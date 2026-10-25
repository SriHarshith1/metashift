import { render, screen } from "@testing-library/react";
import type { Ripple } from "../types/generated";
import Ripples from "./Ripples";

const ripple: Ripple = {
  title: "Lethality marksmen gain",
  explanation: "Crit item nerfs push Caitlyn toward lethality.",
  entities: [
    { entity: "Kai'Sa", entity_type: "champion", icon_url: "https://example.test/Kaisa.png" },
    { entity: "Infinity Edge", entity_type: "item", icon_url: null },
  ],
};

test("Ripples lists each ripple with links to the involved entities", () => {
  const { container } = render(<Ripples game="lol" ripples={[ripple]} />);
  expect(screen.getByRole("heading", { level: 2, name: "Ripple effects" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "Lethality marksmen gain" })).toBeInTheDocument();
  expect(screen.getByText("Crit item nerfs push Caitlyn toward lethality.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Kai'Sa" })).toHaveAttribute("href", `#/lol/champion/${encodeURIComponent("Kai'Sa")}`);
  expect(screen.getByRole("link", { name: "Infinity Edge" })).toHaveAttribute("href", "#/lol/item/Infinity%20Edge");
  expect(container.querySelectorAll("img")).toHaveLength(1);
});

test("Ripples renders nothing without ripples", () => {
  const { container } = render(<Ripples game="lol" ripples={[]} />);
  expect(container).toBeEmptyDOMElement();
});
