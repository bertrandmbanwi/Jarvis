"""
Structured Prompt Template Library

Provides a collection of task-specific prompt templates with built-in scoring
and keyword matching. Templates can be selected based on the request type and
scoring mechanism, enabling consistent and repeatable prompt patterns.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger("jarvis.agent.templates")


@dataclass
class PromptTemplate:
    """Represents a single prompt template with metadata and format string."""
    task_type: str
    keywords: List[str]
    template_format: str
    acceptance_criteria: List[str]
    description: str = ""

    def score_match(self, request_text: str) -> float:
        """
        Score how well this template matches the request.

        Args:
            request_text: User request text to score against

        Returns:
            Match score from 0.0 to 1.0
        """
        if not request_text:
            return 0.0

        request_lower = request_text.lower()
        matching_keywords = sum(
            1 for kw in self.keywords
            if kw.lower() in request_lower
        )

        if not self.keywords:
            return 0.0

        return min(1.0, matching_keywords / len(self.keywords))


@dataclass
class Improvement:
    """Represents a suggested improvement to a template section."""
    section_name: str
    current_content: str
    suggested_change: str
    rationale: str


# Template library initialized with common task types
TEMPLATES: Dict[str, PromptTemplate] = {
    "landing_page": PromptTemplate(
        task_type="landing_page",
        keywords=["landing", "page", "website", "design", "hero", "conversion"],
        description="Generate landing page copy and structure",
        template_format="""\
Task: Create a landing page for {target_audience}

Objective: {objective}

Key selling points:
- {benefit_1}
- {benefit_2}
- {benefit_3}

Call to action: {cta}

Design elements to include:
- Hero section with headline
- Value proposition statement
- Feature list with icons
- Testimonials or social proof
- Footer with contact info

Success metrics: {metrics}
""",
        acceptance_criteria=[
            "Headline is clear and compelling",
            "CTA button is prominent and actionable",
            "Value props are specific and measurable",
            "Design supports mobile and desktop",
            "Load time under 3 seconds",
        ],
    ),
    "bug_fix": PromptTemplate(
        task_type="bug_fix",
        keywords=["bug", "fix", "error", "issue", "broken", "crash"],
        description="Fix a software bug",
        template_format="""\
Bug Report: {bug_title}

Description: {bug_description}

Expected behavior: {expected}

Actual behavior: {actual}

Steps to reproduce:
1. {step_1}
2. {step_2}
3. {step_3}

Environment:
- Version: {version}
- OS: {os}
- Browser: {browser}

Error message: {error_message}

Logs: {logs}

Fix strategy: {strategy}
""",
        acceptance_criteria=[
            "Bug is reproducible from steps provided",
            "Root cause is identified",
            "Fix does not introduce new regressions",
            "Code includes unit test for bug case",
            "Error handling is robust",
        ],
    ),
    "feature": PromptTemplate(
        task_type="feature",
        keywords=["feature", "new", "add", "implement", "build", "create"],
        description="Implement a new feature",
        template_format="""\
Feature Request: {feature_name}

User story:
As a {user_type}
I want to {want}
So that {benefit}

Acceptance criteria:
- {criteria_1}
- {criteria_2}
- {criteria_3}

Technical requirements:
- Stack: {stack}
- Database changes: {db_changes}
- API endpoints: {endpoints}

Design:
- Wireframes: {wireframes}
- UI components: {components}

Test plan:
- Unit tests: {unit_tests}
- Integration tests: {integration_tests}
- E2E tests: {e2e_tests}
""",
        acceptance_criteria=[
            "All acceptance criteria met",
            "Code coverage >= 80%",
            "Performance benchmarks met",
            "Documentation is complete",
            "No breaking changes to existing APIs",
        ],
    ),
    "refactor": PromptTemplate(
        task_type="refactor",
        keywords=["refactor", "improve", "clean", "simplify", "optimize"],
        description="Refactor existing code",
        template_format="""\
Refactoring: {target_module}

Current state:
- Complexity: {complexity}
- Code duplication: {duplication}
- Performance issues: {perf_issues}
- Technical debt: {tech_debt}

Goals:
1. {goal_1}
2. {goal_2}
3. {goal_3}

Scope:
- Files to change: {files}
- Breaking changes: {breaking}

Testing strategy:
- Regression tests: {regression}
- Performance tests: {perf_tests}
- Coverage requirement: {coverage}

Success metrics:
- {metric_1}
- {metric_2}
""",
        acceptance_criteria=[
            "All tests pass",
            "No performance degradation",
            "Code duplication reduced by target %",
            "Complexity metrics improved",
            "Documentation updated",
        ],
    ),
    "research": PromptTemplate(
        task_type="research",
        keywords=["research", "investigate", "explore", "learn", "understand"],
        description="Research and document a topic",
        template_format="""\
Research Topic: {topic}

Research questions:
1. {question_1}
2. {question_2}
3. {question_3}

Scope:
- Time period: {time_period}
- Domains to cover: {domains}
- Geographic focus: {geography}

Deliverables:
- Executive summary
- Detailed findings
- Competitive analysis
- Recommendations

Research methods:
- {method_1}
- {method_2}
- {method_3}

Sources to consult:
- {source_1}
- {source_2}
- {source_3}
""",
        acceptance_criteria=[
            "Research is based on credible sources",
            "Findings are well-documented",
            "Recommendations are actionable",
            "Summary is under 500 words",
            "All sources are cited",
        ],
    ),
    "fullstack_app": PromptTemplate(
        task_type="fullstack_app",
        keywords=["app", "application", "fullstack", "build", "scaffold"],
        description="Build a complete full-stack application",
        template_format="""\
Full-Stack Application: {app_name}

Overview: {description}

Architecture:
- Frontend: {frontend_tech}
- Backend: {backend_tech}
- Database: {database_tech}
- Deployment: {deployment_target}

Feature list:
- {feature_1}
- {feature_2}
- {feature_3}

Database schema:
- {table_1}
- {table_2}
- {table_3}

API endpoints:
- {endpoint_1}
- {endpoint_2}
- {endpoint_3}

UI components:
- {component_1}
- {component_2}
- {component_3}

Security considerations:
- Auth: {auth_method}
- Data validation: {validation}
- Rate limiting: {rate_limit}
""",
        acceptance_criteria=[
            "All core features implemented",
            "API is fully documented",
            "Frontend is responsive",
            "Tests cover >= 80% of code",
            "Deployment is automated",
        ],
    ),
    "api": PromptTemplate(
        task_type="api",
        keywords=["api", "endpoint", "rest", "graphql", "integration"],
        description="Design or implement an API",
        template_format="""\
API Design: {api_name}

Purpose: {purpose}

Base URL: {base_url}

Endpoints:

GET {endpoint_1}
  Description: {desc_1}
  Parameters: {params_1}
  Response: {response_1}

POST {endpoint_2}
  Description: {desc_2}
  Request body: {body_2}
  Response: {response_2}

Authentication:
- Method: {auth_method}
- Header: {auth_header}

Rate limiting:
- Requests per minute: {rpm}
- Burst limit: {burst}

Error handling:
- Status codes: {status_codes}
- Error format: {error_format}

Versioning: {versioning}
""",
        acceptance_criteria=[
            "API follows REST conventions",
            "All endpoints are documented",
            "Request/response examples provided",
            "Error codes are clear",
            "Rate limiting is enforced",
        ],
    ),
}


def get_template(task_type: str, request_text: str = "") -> Optional[PromptTemplate]:
    """
    Get a template by task type, optionally scoring by request text.

    Args:
        task_type: Type of task to get template for
        request_text: Optional request text to score template match

    Returns:
        PromptTemplate if found, else None
    """
    if task_type in TEMPLATES:
        return TEMPLATES[task_type]

    if not request_text:
        return None

    best_match = None
    best_score = 0.0

    for template in TEMPLATES.values():
        score = template.score_match(request_text)
        if score > best_score:
            best_score = score
            best_match = template

    return best_match if best_score > 0.0 else None


def get_template_names() -> List[str]:
    """Get list of all available template names."""
    return list(TEMPLATES.keys())


def fill_template(
    template_str: str,
    safe_defaults: bool = True,
    **kwargs,
) -> str:
    """
    Fill a template string with provided values.

    Args:
        template_str: Template string with {placeholder} format
        safe_defaults: If True, use empty string for missing keys
        **kwargs: Values to substitute in template

    Returns:
        Filled template string

    Raises:
        KeyError: If safe_defaults=False and a placeholder is missing
    """
    try:
        if safe_defaults:
            return template_str.format_map(
                {k: str(v) if v is not None else "" for k, v in kwargs.items()}
            )
        else:
            return template_str.format(**kwargs)
    except KeyError as e:
        if safe_defaults:
            logger.warning("Missing template key: %s, using empty string", e)
            return template_str.format_map(
                {k: str(v) if v is not None else "" for k, v in kwargs.items()}
            )
        raise


def register_template(template: PromptTemplate) -> None:
    """
    Register a new custom template.

    Args:
        template: PromptTemplate instance to register
    """
    TEMPLATES[template.task_type] = template
    logger.info("Registered template: %s", template.task_type)


def list_templates() -> Dict[str, str]:
    """
    List all available templates with descriptions.

    Returns:
        Dict mapping template names to descriptions
    """
    return {
        name: template.description
        for name, template in TEMPLATES.items()
    }
