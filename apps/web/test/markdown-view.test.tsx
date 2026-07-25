import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownView } from "../app/markdown-view";

describe("MarkdownView", () => {
  it("does not render raw HTML or external images", () => {
    const { container } = render(
      <MarkdownView value={'<script>alert("x")</script>\n\n![tracking](https://example.com/pixel.png)'} />,
    );

    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByText("[画像: tracking]")).toBeInTheDocument();
  });

  it("renders safe links and suppresses unsupported schemes", () => {
    render(
      <MarkdownView value={"[safe](https://example.com) [unsafe](javascript:alert(1))"} />,
    );

    expect(screen.getByRole("link", { name: "safe" })).toHaveAttribute(
      "href",
      "https://example.com",
    );
    expect(screen.queryByRole("link", { name: "unsafe" })).not.toBeInTheDocument();
  });
});
