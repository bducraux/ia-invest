import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { OwnerBadge } from "@/components/members/owner-badge";

describe("OwnerBadge", () => {
  it("renders the owner display name when present", () => {
    render(
      <OwnerBadge
        owner={{ id: "bob", name: "Bob", displayName: "Brunão", status: "active" }}
      />,
    );
    expect(screen.getByText("Brunão")).toBeInTheDocument();
  });

  it("falls back to name when displayName is empty", () => {
    render(<OwnerBadge owner={{ id: "alice", name: "Alice", status: "active" }} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders an em-dash when owner is null", () => {
    render(<OwnerBadge owner={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
