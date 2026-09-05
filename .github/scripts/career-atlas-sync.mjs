import { createHmac } from 'node:crypto';
import { pathToFileURL } from 'node:url';
export const repositories = [
  ['azure', 'terraform-azure-platform'],
  ['runner', 'actions-runner-control-plane'],
  ['infra', 'infraguard'],
  ['gitops', 'gitops-supply-chain'],
  ['code', 'codeguard'],
  ['status', 'status-page'],
  ['jarvis', 'Jarvis'],
];
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function github(path, token) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetch(
      `https://api.github.com/repos/bertrandmbanwi/${path}`,
      {
        headers: {
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'Bertrand-Career-Atlas',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: AbortSignal.timeout(25000),
      },
    );
    if (response.ok) return response.json();
    if (response.status === 403 && token) return github(path, null);
    if ((response.status >= 500 || response.status === 429) && attempt < 2) {
      await pause((attempt + 1) * 2000);
      continue;
    }
    throw new Error(`GitHub check returned HTTP ${response.status}.`);
  }
  throw new Error('GitHub check could not complete.');
}
export async function collectRepository(projectId, repo, token) {
  try {
    const meta = await github(repo, token);
    if (
      meta.private ||
      meta.visibility !== 'public' ||
      meta.full_name !== `bertrandmbanwi/${repo}`
    )
      throw new Error('Repository is no longer an allowlisted public source.');
    const branch = encodeURIComponent(meta.default_branch);
    const [commits, releases, runs] = await Promise.all([
      github(`${repo}/commits?sha=${branch}&per_page=1`, token),
      github(`${repo}/releases?per_page=1`, token),
      github(`${repo}/actions/runs?branch=${branch}&per_page=20`, token),
    ]);
    const commit = commits[0];
    if (!commit) throw new Error('No default-branch commit found.');
    const release = releases.find((item) => !item.draft);
    const run = runs.workflow_runs?.find(
      (item) =>
        !['Update Career Atlas', 'Career Atlas event update'].includes(
          item.name,
        ),
    );
    return {
      repo,
      error: null,
      data: {
        repo,
        projectId,
        description: (meta.description ?? '').slice(0, 1000),
        defaultBranch: meta.default_branch,
        community: { stars: meta.stargazers_count, forks: meta.forks_count },
        head: {
          sha: commit.sha,
          message:
            commit.commit.message.split('\n')[0].slice(0, 500) ||
            'Repository update',
          at: commit.commit.committer.date,
          url: commit.html_url,
        },
        release: release
          ? {
              tag: release.tag_name.slice(0, 150),
              at: release.published_at,
              url: release.html_url,
            }
          : null,
        workflow: run
          ? {
              name: (run.name || 'Workflow').slice(0, 150),
              status: run.status,
              conclusion: run.conclusion,
              at: run.updated_at,
              url: run.html_url,
              sha: run.head_sha,
            }
          : null,
      },
    };
  } catch (error) {
    return {
      repo,
      data: null,
      error:
        error instanceof Error
          ? error.message.slice(0, 300)
          : 'Repository check failed.',
    };
  }
}
export async function main() {
  const {
    GITHUB_TOKEN,
    SITE_URL,
    SITE_ACCESS_TOKEN,
    PORTFOLIO_SYNC_SECRET,
    GITHUB_RUN_ID,
    GITHUB_RUN_ATTEMPT,
    GITHUB_REPOSITORY,
    PORTFOLIO_AUTH,
    ACTIONS_ID_TOKEN_REQUEST_URL,
    ACTIONS_ID_TOKEN_REQUEST_TOKEN,
  } = process.env;
  const oidc = PORTFOLIO_AUTH === 'github-oidc';
  if (
    !GITHUB_TOKEN ||
    !SITE_URL ||
    (!oidc && (!SITE_ACCESS_TOKEN || !PORTFOLIO_SYNC_SECRET)) ||
    (oidc &&
      (!ACTIONS_ID_TOKEN_REQUEST_URL || !ACTIONS_ID_TOKEN_REQUEST_TOKEN)) ||
    !GITHUB_RUN_ID
  )
    throw new Error('The scheduler configuration is incomplete.');
  const site = new URL(SITE_URL);
  if (site.protocol !== 'https:' || site.username || site.password)
    throw new Error('Invalid Site URL.');
  const checkedAt = new Date().toISOString();
  const selected = oidc
    ? repositories.filter(
        ([, repo]) => GITHUB_REPOSITORY === `bertrandmbanwi/${repo}`,
      )
    : repositories;
  if (oidc && selected.length !== 1)
    throw new Error('Unrecognized event repository.');
  const results = [];
  // Bound external requests while keeping each repository failure independent.
  for (const [projectId, repo] of selected)
    results.push(await collectRepository(projectId, repo, GITHUB_TOKEN));
  const payload = {
    version: 1,
    runId: `${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT ?? 1}`,
    checkedAt,
    sourceUrl: `https://github.com/${oidc ? GITHUB_REPOSITORY : 'bertrandmbanwi/career-atlas-automation'}/actions/runs/${GITHUB_RUN_ID}`,
    repositories: results,
  };
  const body = JSON.stringify(payload);
  let delivered = false;
  for (let attempt = 0; attempt < 3; attempt++) {
    const timestamp = String(Date.now());
    const signature = oidc
      ? null
      : createHmac('sha256', PORTFOLIO_SYNC_SECRET)
          .update(`${timestamp}.${body}`)
          .digest('hex');
    try {
      let auth;
      if (oidc) {
        const identityUrl = new URL(ACTIONS_ID_TOKEN_REQUEST_URL);
        identityUrl.searchParams.set(
          'audience',
          new URL('/api/sync', site).href,
        );
        const identityResponse = await fetch(identityUrl, {
          headers: {
            Authorization: `Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}`,
          },
          signal: AbortSignal.timeout(15000),
          redirect: 'error',
        });
        if (!identityResponse.ok)
          throw new Error('GitHub identity could not be obtained.');
        const { value } = await identityResponse.json();
        if (!value) throw new Error('GitHub identity is missing.');
        auth = { 'X-GitHub-OIDC-Token': value };
      } else
        auth = {
          'OAI-Sites-Authorization': `Bearer ${SITE_ACCESS_TOKEN}`,
          'X-Portfolio-Timestamp': timestamp,
          'X-Portfolio-Signature': signature,
        };
      const response = await fetch(new URL('/api/sync', site), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...auth,
        },
        body,
        redirect: 'error',
        signal: AbortSignal.timeout(45000),
      });
      if (response.ok) {
        const receipt = await response.json();
        if (!receipt.status) throw new Error('Unexpected sync receipt.');
        console.log(`Portfolio update accepted: ${receipt.status}.`);
        delivered = true;
        break;
      }
      console.error(
        `Delivery attempt ${attempt + 1} returned HTTP ${response.status}.`,
      );
    } catch {
      console.error(`Delivery attempt ${attempt + 1} did not complete.`);
    }
    if (attempt < 2) await pause((attempt + 1) * 5000);
  }
  if (!delivered)
    throw new Error(
      'Portfolio delivery failed. Previous data remains available; the next scheduled run will retry.',
    );
  const failed = results.filter((item) => item.error);
  for (const item of failed) console.error(`${item.repo}: ${item.error}`);
  if (failed.length)
    throw new Error(
      `${failed.length} repository check(s) need attention. Successful checks were delivered.`,
    );
  console.log(
    `Checked ${results.length} public repositories. Descriptive content remains subject to owner review.`,
  );
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
