import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import fixtureJson from "../test/fixtures/report-26.21.json";
import type { ReportFile } from "../types/generated";
import ReportPage from "./ReportPage";

vi.mock("../data", () => ({ fetchReport: vi.fn() }));
import { fetchReport } from "../data";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/lol/26.21"]}>
      <Routes>
        <Route path="/:game/:patch" element={<ReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("ReportPage header shows patch, comparison, headline, themes and warnings", async () => {
  vi.mocked(fetchReport).mockResolvedValue(fixtureJson as ReportFile);
  renderPage();
  expect(await screen.findByRole("heading", { level: 1, name: "Patch 26.21 · vs 26.20 meta" })).toBeInTheDocument();
  expect(screen.getByText(/Azir and Nunu gain strength/)).toBeInTheDocument();
  expect(screen.getByText("Marksman nerfs")).toBeInTheDocument();
  expect(screen.getByText(/warnings \(2\)/i)).toBeInTheDocument();
  expect(fetchReport).toHaveBeenCalledWith("lol", "26.21");
});

test("ReportPage says no previous patch when compared_to is null", async () => {
  vi.mocked(fetchReport).mockResolvedValue({ ...(fixtureJson as ReportFile), compared_to: null, warnings: [] });
  renderPage();
  expect(await screen.findByRole("heading", { level: 1, name: "Patch 26.21 · no previous patch" })).toBeInTheDocument();
  expect(screen.queryByText(/warnings/i)).not.toBeInTheDocument();
});

test("ReportPage shows the load error", async () => {
  vi.mocked(fetchReport).mockRejectedValue(new Error("could not load data/lol/26.21.json"));
  renderPage();
  expect(await screen.findByText("could not load data/lol/26.21.json")).toBeInTheDocument();
});

test("ReportPage shows ripple effects when the report has them", async () => {
  const ripples = [{ title: "Tanks breathe", explanation: "Marksman nerfs help tanks.", entities: [] }];
  vi.mocked(fetchReport).mockResolvedValue({ ...(fixtureJson as ReportFile), ripples });
  renderPage();
  expect(await screen.findByRole("heading", { level: 2, name: "Ripple effects" })).toBeInTheDocument();
  expect(screen.getByText("Marksman nerfs help tanks.")).toBeInTheDocument();
});

test("ReportPage hides ripple effects for older reports", async () => {
  vi.mocked(fetchReport).mockResolvedValue(fixtureJson as ReportFile);
  renderPage();
  await screen.findByRole("heading", { level: 1 });
  expect(screen.queryByText("Ripple effects")).not.toBeInTheDocument();
});
