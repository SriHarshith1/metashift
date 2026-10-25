import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Change, EntityVerdict } from "../types/generated";
import EntityCard from "./EntityCard";

const v: EntityVerdict = {
  entity: "Kai'Sa",
  entity_type: "champion",
  verdict: "fall",
  confidence: "high",
  previous: { win_rate: 51.3, pick_rate: 11.6, ban_rate: 7.9, tier: "S" },
  reason: "Lower missile damage hits a popular marksman.",
  change_refs: [0],
  icon_url: "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/champion/Kaisa.png",
};
const c: Change = {
  entity: "Kai'Sa",
  entity_type: "champion",
  target: "Q - Icathian Rain",
  stat: "Damage per missile",
  old: "40",
  new: "35",
  direction: "nerf",
  source_quote: "Damage per missile: 40 ⇒ 35",
};

test("EntityCard expands source changes with null-safe values", async () => {
  const user = userEvent.setup();
  render(<EntityCard verdict={v} changes={[{ ...c, old: null, new: "45" }]} />);
  expect(screen.queryByText("— → 45")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /show changes/i }));
  expect(screen.getByText("— → 45")).toBeInTheDocument();
  expect(screen.getByText("Q - Icathian Rain")).toBeInTheDocument();
  expect(screen.getByText("Damage per missile")).toBeInTheDocument();
  expect(screen.getByText("Damage per missile: 40 ⇒ 35")).toBeInTheDocument();
  expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /hide changes/i }));
  expect(screen.queryByText("— → 45")).not.toBeInTheDocument();
});

test("EntityCard shows a dash when the new value is missing", async () => {
  const user = userEvent.setup();
  render(<EntityCard verdict={v} changes={[{ ...c, new: null }]} />);
  await user.click(screen.getByRole("button", { name: /show changes/i }));
  expect(screen.getByText("40 → —")).toBeInTheDocument();
});

test("EntityCard links to entity history with encoded name", () => {
  render(<EntityCard game="lol" verdict={v} changes={[c]} />);
  expect(screen.getByRole("link", { name: "Kai'Sa" })).toHaveAttribute("href", `#/lol/champion/${encodeURIComponent("Kai'Sa")}`);
  render(<EntityCard game="lol" verdict={{ ...v, entity: "Nunu & Willump" }} changes={[]} />);
  expect(screen.getByRole("link", { name: "Nunu & Willump" })).toHaveAttribute("href", "#/lol/champion/Nunu%20%26%20Willump");
});

test("EntityCard shows previous tier, win rate, confidence and reason", () => {
  render(<EntityCard verdict={v} changes={[c]} />);
  expect(screen.getByText(/tier S/)).toBeInTheDocument();
  expect(screen.getByText(/51\.3%/)).toBeInTheDocument();
  expect(screen.getByText(/high confidence/i)).toBeInTheDocument();
  expect(screen.getByText("Lower missile damage hits a popular marksman.")).toBeInTheDocument();
  expect(screen.getByText(/fall/i)).toBeInTheDocument();
});

test("EntityCard shows the icon, and no image when icon_url is null", () => {
  const { container, rerender } = render(<EntityCard verdict={v} changes={[c]} />);
  expect(container.querySelector("img")).toHaveAttribute("src", v.icon_url);
  expect(container.querySelector("img")).toHaveAttribute("alt", "");
  rerender(<EntityCard verdict={{ ...v, icon_url: null }} changes={[c]} />);
  expect(container.querySelector("img")).toBeNull();
});

test("EntityCard says no stats when previous is null", () => {
  render(<EntityCard verdict={{ ...v, previous: null }} changes={[c]} />);
  expect(screen.getByText(/no stats/i)).toBeInTheDocument();
  expect(screen.queryByText(/null/)).not.toBeInTheDocument();
});

test("EntityCard shows impact and build shift when present", () => {
  const { rerender } = render(
    <EntityCard verdict={{ ...v, impact: "Less burst in lane.", build_shift: "Lethality builds gain value." }} changes={[c]} />,
  );
  expect(screen.getByText("Less burst in lane.")).toBeInTheDocument();
  expect(screen.getByText("Lethality builds gain value.")).toBeInTheDocument();
  expect(screen.getByText("Build shift")).toBeInTheDocument();
  rerender(<EntityCard verdict={{ ...v, impact: null, build_shift: null }} changes={[c]} />);
  expect(screen.queryByText("Impact")).not.toBeInTheDocument();
  expect(screen.queryByText("Build shift")).not.toBeInTheDocument();
});
