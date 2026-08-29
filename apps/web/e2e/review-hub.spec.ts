import { expect, test } from "@playwright/test";

test("findings, markdown, manual registration, transitions, and runs", async ({
  page,
  request,
}) => {
  const suffix = Date.now().toString();
  const repository = `e2e/repository-${suffix}`;
  const createGuideline = await request.post("/api/v1/review-guidelines", {
    data: {
      title: `E2E guideline ${suffix}`,
      content_markdown: "- Correctness\n- Security",
    },
  });
  expect(createGuideline.ok()).toBeTruthy();
  const reviewGuidelineId = (await createGuideline.json()).display_id;
  const reconciliation = {
    repository,
    review_guideline_id: reviewGuidelineId,
    base_branch: "main",
    target_branch: "feature/e2e",
    commit_sha: suffix,
    reviewed_file_count: 1,
    review_source: "Codex",
    detected_at: new Date().toISOString(),
    findings: [
      {
        title: `Automated finding ${suffix}`,
        description: "Evidence with **Markdown**.\n\n## 修正案\n\nUse `safe_call()`.\n\n```python\nunsafe_call()\n```",
        severity: "High",
        category: "Correctness",
        rule_id: "E2E-AUTO-001",
        file_path: "src/e2e.py",
        symbol: "run",
        line_number: 12,
        code_context: "unsafe_call()",
        code_language: "python",
        ai_confidence: 95,
      },
    ],
  };

  const dryRun = await request.post("/api/v1/reconciliations/dry-run", {
    data: reconciliation,
  });
  expect(dryRun.ok()).toBeTruthy();
  expect((await dryRun.json()).results[0].action).toBe("would_create");

  const apply = await request.post("/api/v1/reconciliations", {
    data: reconciliation,
    headers: { "Idempotency-Key": `${repository}:${suffix}:Codex` },
  });
  expect(apply.ok()).toBeTruthy();

  await page.goto("/");
  await expect(page.getByText(`Automated finding ${suffix}`)).toBeVisible();
  await page.getByRole("button", { name: new RegExp(`Automated finding ${suffix}`) }).click();
  await expect(page.getByText("unsafe_call()").first()).toBeVisible();
  await page.getByRole("button", { name: "詳細を拡大" }).click();
  await expect(page.getByRole("button", { name: "一覧を表示" })).toBeVisible();
  await expect(page.locator(".finding-list")).toBeHidden();
  await page.getByRole("button", { name: "一覧を表示" }).click();
  await expect(page.locator(".finding-list")).toBeVisible();
  const timeline = page.locator(".timeline-details");
  await expect(timeline).not.toHaveAttribute("open", "");
  await timeline.getByText("変更履歴").click();
  await expect(timeline).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "Markdown" }).click();
  await expect(page.getByText(/```python/)).toBeVisible();

  await page.getByRole("button", { name: "有識者指摘" }).click();
  await page.getByRole("combobox", { name: "Repository" }).selectOption(repository);
  await page.getByRole("textbox", { name: "タイトル" }).fill(`Human finding ${suffix}`);
  await page.getByRole("textbox", { name: "ファイルパス" }).fill("src/human.py");
  await page.getByRole("textbox", { name: "シンボル" }).fill("check");
  await page.getByRole("textbox", { name: "指摘内容（Markdown）" }).fill("Human evidence\n\n## 修正案\n\nFix it");
  await page.getByRole("button", { name: "登録", exact: true }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`Human finding ${suffix}`) }),
  ).toBeVisible();

  const status = page.locator(".detail-panel").getByRole("combobox").first();
  await status.selectOption("対応予定");
  await expect(status).toHaveValue("対応予定");

  await page.getByRole("button", { name: "レビュー履歴" }).click();
  await expect(page.getByText(repository).first()).toBeVisible();
});
