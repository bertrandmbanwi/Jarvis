(() => {
  if (window.__jarvisContentScriptLoaded) return;
  window.__jarvisContentScriptLoaded = true;

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type !== "command") return false;

    handleCommand(msg)
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: e.message }));

    return true; // Keep the message channel open for async response
  });

  async function handleCommand(msg) {
    switch (msg.action) {
      case "click":
        return handleClick(msg);
      case "type":
        return handleType(msg);
      case "select":
        return handleSelect(msg);
      case "scroll":
        return handleScroll(msg);
      case "read_page":
        return handleReadPage(msg);
      case "read_element":
        return handleReadElement(msg);
      case "find_elements":
        return handleFindElements(msg);
      case "fill_form":
        return handleFillForm(msg);
      case "wait_for":
        return handleWaitFor(msg);
      default:
        return { success: false, error: `Unknown content action: ${msg.action}` };
    }
  }

  function findElement(target) {
    if (!target) return null;

    if (target.selector) {
      const el = document.querySelector(target.selector);
      if (el) return el;
    }

    if (target.text) {
      const text = target.text.toLowerCase().trim();
      const index = target.index || 0;

      const interactiveSelectors = [
        "a", "button", "input[type='submit']", "input[type='button']",
        "[role='button']", "[role='link']", "[role='tab']",
        "h1", "h2", "h3", "h4", "h5", "h6",
      ];

      const candidates = [];
      for (const sel of interactiveSelectors) {
        document.querySelectorAll(sel).forEach((el) => {
          const elText = (el.textContent || el.value || el.getAttribute("aria-label") || "")
            .toLowerCase().trim();
          if (elText.includes(text)) {
            candidates.push(el);
          }
        });
      }

      if (candidates.length === 0) {
        const walker = document.createTreeWalker(
          document.body,
          NodeFilter.SHOW_ELEMENT,
          {
            acceptNode: (node) => {
              if (node.offsetParent === null && getComputedStyle(node).position !== "fixed") {
                return NodeFilter.FILTER_REJECT; // Hidden
              }
              const nodeText = (node.textContent || "").toLowerCase().trim();
              return nodeText.includes(text) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
            },
          }
        );

        while (walker.nextNode()) {
          candidates.push(walker.currentNode);
        }
      }

      if (candidates.length > index) {
        return candidates[index];
      }
    }

    if (target.ariaLabel) {
      const el = document.querySelector(`[aria-label="${CSS.escape(target.ariaLabel)}"]`);
      if (el) return el;
    }

    if (target.coordinate && Array.isArray(target.coordinate)) {
      const [x, y] = target.coordinate;
      return document.elementFromPoint(x, y);
    }

    return null;
  }

  function findElements(target, limit = 20) {
    const results = [];

    if (target.selector) {
      document.querySelectorAll(target.selector).forEach((el, i) => {
        if (i < limit) results.push(el);
      });
    }

    if (target.text && results.length === 0) {
      const text = target.text.toLowerCase().trim();
      const allElements = document.querySelectorAll("*");
      for (const el of allElements) {
        if (results.length >= limit) break;
        const elText = (el.textContent || "").toLowerCase().trim();
        if (elText.includes(text) && el.children.length < 5) {
          results.push(el);
        }
      }
    }

    return results;
  }

  function describeElement(el) {
    const tag = el.tagName.toLowerCase();
    const id = el.id ? `#${el.id}` : "";
    const classes = el.className && typeof el.className === "string"
      ? `.${el.className.trim().split(/\s+/).slice(0, 3).join(".")}`
      : "";
    const text = (el.textContent || "").trim().slice(0, 80);
    const href = el.getAttribute("href") || "";
    const ariaLabel = el.getAttribute("aria-label") || "";

    return {
      tag,
      selector: `${tag}${id}${classes}`.slice(0, 120),
      text: text || undefined,
      href: href || undefined,
      ariaLabel: ariaLabel || undefined,
      rect: el.getBoundingClientRect().toJSON(),
      visible: isVisible(el),
    };
  }

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
    return true;
  }

  async function handleClick(msg) {
    const el = findElement(msg.target || msg);
    if (!el) {
      return { success: false, error: "Element not found for click." };
    }

    el.scrollIntoView({ behavior: "smooth", block: "center" });
    await sleep(200);

    el.focus();
    el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
    el.click();

    return {
      success: true,
      data: {
        clicked: describeElement(el),
        url: window.location.href,
      },
    };
  }

  async function handleType(msg) {
    const target = msg.target || msg;
    const el = findElement(target);
    if (!el) {
      return { success: false, error: "Element not found for typing." };
    }

    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.focus();

    if (msg.clear || target.clear) {
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        el.value = "";
      } else if (el.isContentEditable) {
        el.textContent = "";
      }
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }

    const text = msg.text || target.text || "";
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      el.value += text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (el.isContentEditable) {
      document.execCommand("insertText", false, text);
    }

    return {
      success: true,
      data: {
        typed: text.slice(0, 100),
        element: describeElement(el),
      },
    };
  }

  async function handleSelect(msg) {
    const target = msg.target || msg;
    const el = findElement(target);
    if (!el || el.tagName !== "SELECT") {
      return { success: false, error: "SELECT element not found." };
    }

    const value = msg.value || target.value;
    const text = msg.optionText || target.optionText;

    if (value !== undefined) {
      el.value = value;
    } else if (text) {
      const option = Array.from(el.options).find(
        (o) => o.textContent.trim().toLowerCase() === text.toLowerCase()
      );
      if (option) {
        el.value = option.value;
      } else {
        return { success: false, error: `Option "${text}" not found in select.` };
      }
    }

    el.dispatchEvent(new Event("change", { bubbles: true }));
    return { success: true, data: { selected: el.value } };
  }

  async function handleScroll(msg) {
    const direction = msg.direction || "down";
    const amount = msg.amount || 3;
    const pixels = amount * 200;

    let target = document;
    if (msg.selector || (msg.target && msg.target.selector)) {
      const sel = msg.selector || msg.target.selector;
      target = document.querySelector(sel) || document;
    }

    const scrollEl = target === document ? window : target;

    switch (direction) {
      case "down":
        scrollEl.scrollBy({ top: pixels, behavior: "smooth" });
        break;
      case "up":
        scrollEl.scrollBy({ top: -pixels, behavior: "smooth" });
        break;
      case "left":
        scrollEl.scrollBy({ left: -pixels, behavior: "smooth" });
        break;
      case "right":
        scrollEl.scrollBy({ left: pixels, behavior: "smooth" });
        break;
    }

    await sleep(300);
    return {
      success: true,
      data: {
        scrolled: direction,
        amount,
        scrollY: window.scrollY,
        scrollHeight: document.body.scrollHeight,
      },
    };
  }

  async function handleReadPage(msg) {
    const format = msg.format || "text";

    if (format === "html") {
      return {
        success: true,
        data: {
          html: document.documentElement.outerHTML.slice(0, 50000),
          url: window.location.href,
          title: document.title,
        },
      };
    }

    if (format === "markdown" || format === "text") {
      const textParts = [];
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode: (node) => {
            const parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_REJECT;
            const tag = parent.tagName;
            if (["SCRIPT", "STYLE", "NOSCRIPT", "SVG"].includes(tag)) {
              return NodeFilter.FILTER_REJECT;
            }
            if (!isVisible(parent)) return NodeFilter.FILTER_REJECT;
            const trimmed = node.textContent.trim();
            return trimmed.length > 0 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
          },
        }
      );

      while (walker.nextNode()) {
        textParts.push(walker.currentNode.textContent.trim());
      }

      const links = [];
      document.querySelectorAll("a[href]").forEach((a) => {
        if (isVisible(a)) {
          links.push({
            text: a.textContent.trim().slice(0, 100),
            href: a.href,
          });
        }
      });

      return {
        success: true,
        data: {
          text: textParts.join("\n").slice(0, 30000),
          links: links.slice(0, 50),
          url: window.location.href,
          title: document.title,
        },
      };
    }

    return { success: false, error: `Unknown format: ${format}` };
  }

  async function handleReadElement(msg) {
    const target = msg.target || msg;
    const el = findElement(target);
    if (!el) {
      return { success: false, error: "Element not found." };
    }

    const attr = msg.attribute || target.attribute;
    if (attr) {
      return { success: true, data: { value: el.getAttribute(attr) } };
    }

    return {
      success: true,
      data: {
        ...describeElement(el),
        innerHTML: el.innerHTML.slice(0, 5000),
        value: el.value || undefined,
      },
    };
  }

  async function handleFindElements(msg) {
    const target = msg.target || msg;
    const limit = msg.limit || 20;
    const elements = findElements(target, limit);

    return {
      success: true,
      data: {
        count: elements.length,
        elements: elements.map(describeElement),
      },
    };
  }

  async function handleFillForm(msg) {
    const fields = msg.fields || {};
    const results = [];

    for (const [selector, value] of Object.entries(fields)) {
      const el = document.querySelector(selector);
      if (!el) {
        results.push({ selector, success: false, error: "Not found" });
        continue;
      }

      if (el.tagName === "SELECT") {
        el.value = value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else if (el.type === "checkbox" || el.type === "radio") {
        el.checked = Boolean(value);
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        el.value = value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }

      results.push({ selector, success: true, value });
    }

    return { success: true, data: { filled: results } };
  }

  async function handleWaitFor(msg) {
    const target = msg.target || msg;
    const timeout = msg.timeout || 10000;
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      const el = findElement(target);
      if (el && isVisible(el)) {
        return { success: true, data: { found: describeElement(el) } };
      }
      await sleep(250);
    }

    return { success: false, error: `Element not found within ${timeout}ms.` };
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  console.log("[JARVIS] Content script loaded on:", window.location.href);
})();
