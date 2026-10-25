import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fixtureJson from "../test/fixtures/report-26.21.json";
import type { ReportFile } from "../types/generated";
import Board from "./Board";

const fixture = fixtureJson as ReportFile; // 2 rise, 1 stable, 1 fall

test("Board groups verdicts into columns with counts", () => {
  render(<Board report={fixture} />);
  expect(screen.getByRole("heading", { name: /rise \(2\)/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /stable \(1\)/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /fall \(1\)/i })).toBeInTheDocument();
  const rise = screen.getByRole("region", { name: /rise/i });
  expect(within(rise).getByRole("link", { name: "Azir" })).toBeInTheDocument();
  expect(within(rise).getByRole("link", { name: "Nunu & Willump" })).toBeInTheDocument();
  const fall = screen.getByRole("region", { name: /fall/i });
  expect(within(fall).getByRole("link", { name: "Kai'Sa" })).toBeInTheDocument();
});

test("confidence filter hides low-confidence cards", async () => {
  const user = userEvent.setup();
  render(<Board report={fixture} />);
  expect(screen.getByRole("link", { name: "Bastion Breaker" })).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText(/confidence/i), "high");
  expect(screen.queryByRole("link", { name: "Bastion Breaker" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Nunu & Willump" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Azir" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /rise \(1\)/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /stable \(0\)/i })).toBeInTheDocument();
});

test("entity type filter lists the types in the report and filters cards", async () => {
  const user = userEvent.setup();
  render(<Board report={fixture} />);
  const select = screen.getByLabelText(/entity type/i);
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["All types", "champion", "item"]);
  await user.selectOptions(select, "item");
  expect(screen.getByRole("link", { name: "Bastion Breaker" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Azir" })).not.toBeInTheDocument();
});

test("below 640px the board is three tabs and Rise is selected by default", async () => {
  const user = userEvent.setup();
  render(<Board report={fixture} />);
  const tabs = screen.getAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["▲ Rise 2", "● Stable 1", "▼ Fall 1"]);
  expect(screen.getByRole("tab", { name: /rise/i })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("region", { name: /rise/i })).toHaveAttribute("data-active", "true");
  expect(screen.getByRole("region", { name: /fall/i })).toHaveAttribute("data-active", "false");
  await user.click(screen.getByRole("tab", { name: /fall/i }));
  expect(screen.getByRole("tab", { name: /fall/i })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("region", { name: /fall/i })).toHaveAttribute("data-active", "true");
  expect(screen.getByRole("region", { name: /rise/i })).toHaveAttribute("data-active", "false");
});

test("an empty column says so", async () => {
  const user = userEvent.setup();
  render(<Board report={fixture} />);
  await user.selectOptions(screen.getByLabelText(/confidence/i), "high");
  expect(within(screen.getByRole("region", { name: /stable/i })).getByText(/no stable verdicts/i)).toBeInTheDocument();
});
