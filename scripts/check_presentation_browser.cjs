/* Optional local QA with an already available Playwright runtime; no package install. */
const { chromium } = require(
  process.env.ORCIFY_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");

(async () => {
  const root = path.resolve(__dirname, "..");
  const output = path.join(root, "var", "presentation-qa");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.ORCIFY_BROWSER_EXECUTABLE
      ? { executablePath: process.env.ORCIFY_BROWSER_EXECUTABLE }
      : {}),
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    const errors = [];
    const apiRequests = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (request.url().includes("/api/v1/")) apiRequests.push(request.url());
    });
    await page.goto(
      process.env.ORCIFY_PRESENTATION_URL || "http://127.0.0.1:5173/",
      { waitUntil: "networkidle" },
    );
    await page
      .getByRole("heading", { level: 1, name: /One requirement changes/ })
      .waitFor();
    await page.screenshot({
      path: path.join(output, "overview-desktop.png"),
      fullPage: true,
    });
    await page
      .getByRole("link", { name: "Graph & impact", exact: true })
      .click();
    await page
      .getByText("SIMULATED · OFFLINE PREVIEW.", { exact: true })
      .waitFor();
    await page.getByRole("button", { name: /Preview slogan change/ }).click();
    assert.equal(await page.locator(".graph-node.impact-recompute").count(), 3);
    assert.equal(await page.locator(".graph-node.impact-review").count(), 2);
    await page.locator('.react-flow__node[data-id="social_export"]').click();
    await page.getByText(/SOFT impact unknown/).waitFor();
    await page.screenshot({
      path: path.join(output, "graph-impact-desktop.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: /Reset demo/ }).click();
    assert.equal(await page.locator(".graph-node.impact-recompute").count(), 0);
    await page.getByRole("button", { name: /Preview slogan change/ }).click();
    assert.equal(await page.locator(".graph-node.impact-recompute").count(), 3);
    await page
      .getByRole("link", { name: "Experiments & results", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Immediate recomputation", exact: true })
      .waitFor();
    await page.screenshot({
      path: path.join(output, "results-pilot-desktop.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: /R1.3.*Review & replan/ }).click();
    for (const code of ["S01", "S02", "S03", "S04"]) {
      await page.getByRole("button", { name: new RegExp(`${code} ·`) }).click();
    }
    await page.getByText("MMMM", { exact: true }).waitFor();
    const row = page
      .getByRole("row")
      .filter({
        has: page.getByRole("rowheader", { name: "GAMO-CA", exact: true }),
      });
    assert.equal(await row.first().locator("td").first().textContent(), "20");
    await page.screenshot({
      path: path.join(output, "results-workflow-desktop.png"),
      fullPage: true,
    });
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: /R1.1.*Pilot results/ }).click();
    const download = await downloadPromise;
    const savedPath = path.join(output, "downloaded-pilot-results.csv");
    await download.saveAs(savedPath);
    assert.deepEqual(
      await fs.readFile(savedPath),
      await fs.readFile(
        path.join(root, "docs/research/r1_1-pilot/results.csv"),
      ),
    );
    for (let mask = 0; mask < 16; mask++) {
      let material = 0;
      for (let index = 0; index < 4; index++) {
        const desired = Boolean(mask & (1 << index));
        const branch = page.getByRole("button", {
          name: new RegExp(`S0${index + 1} ·`),
        });
        if (
          ((await branch.getAttribute("aria-pressed")) === "true") !==
          desired
        )
          await branch.click();
        if (desired) material++;
      }
      const methodRows = page.getByRole("row");
      for (const method of ["GAMO-CA", "Field-aware DAG"]) {
        const methodRow = methodRows
          .filter({
            has: page.getByRole("rowheader", { name: method, exact: true }),
          })
          .first();
        assert.equal(
          await methodRow.locator("td").first().textContent(),
          String(12 + 2 * material),
        );
      }
    }
    await page.getByRole("button", { name: /R1.2.*Cost sensitivity/ }).click();
    await page.getByLabel("Planning units / millisecond").selectOption("1");
    await page
      .getByText(
        "Conventional DAG has a lower or equal hypothetical total here.",
        { exact: true },
      )
      .waitFor();
    await page.setViewportSize({ width: 1280, height: 800 });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "laptop page overflows",
    );
    await page
      .getByRole("link", { name: "Research overview", exact: true })
      .click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "mobile overview overflows",
    );
    await page.screenshot({
      path: path.join(output, "overview-mobile.png"),
      fullPage: true,
    });
    await page
      .getByRole("link", { name: "Graph & impact", exact: true })
      .click();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "mobile explorer overflows",
    );
    await page.getByRole("button", { name: /Preview slogan change/ }).click();
    await page.getByRole("button", { name: /Live API/ }).click();
    await page.getByLabel("Development access token").waitFor();
    await page
      .getByRole("button", { name: "Presentation demo", exact: true })
      .click();
    await page
      .getByRole("link", { name: "Experiments & results", exact: true })
      .click();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "mobile results overflows",
    );
    await page.screenshot({
      path: path.join(output, "results-mobile.png"),
      fullPage: true,
    });
    assert.deepEqual(apiRequests, [], "offline flow must not call the API");
    assert.deepEqual(errors, [], "browser page errors");
    console.log(
      "Browser checks passed: navigation, saved impact actions/reasons, reset/repeat, 16-outcome controls, sensitivity, byte-identical CSV download, laptop/mobile overflow, and explicit live login. No API calls or page errors in the offline flow.",
    );
    console.log(`Screenshots: ${output}`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
