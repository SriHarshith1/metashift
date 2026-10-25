import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import type { Change, EntityVerdict, IndexFile, ReportFile } from "../types/generated";
import EntityHistory from "./EntityHistory";

vi.mock("../data", () => ({ fetchIndex: vi.fn(), fetchReport: vi.fn() }));
import { fetchIndex, fetchReport } from "../data";

function change(entity: string, stat: string, old: string | null, next: string | null): Change {
  return { entity, entity_type: "champion", target: "Q", stat, old, new: next, direction: "buff", source_quote: `${stat}: ${old} to ${next}` };
}

function report(patch: string, entity: string, extra: Partial<EntityVerdict> = {}): ReportFile {
  return {
    game: "lol",
    patch,
    compared_to: null,
    generated_at: "2026-10-01T00:00:00Z",
    llm: "test",
    headline: `Headline ${patch}`,
    themes: [],
    entities: [
      {
        entity,
        entity_type: "champion",
        verdict: "rise",
        confidence: "medium",
        previous: { win_rate: 48.5, pick_rate: 5, ban_rate: 1, tier: "B" },
        reason: "reason",
        change_refs: [0],
        icon_url: null,
        ...extra,
      },
    ],
    changes: [change(entity, "Damage", patch === "26.19" ? null : "40", "45")],
    warnings: [],
  };
}

const index: IndexFile = {
  games: {
    lol: ["26.19", "26.20", "26.21"].map((patch) => ({ patch, patch_date: null, headline: "", buffs: 1, nerfs: 0, llm: "test" })),
  },
};

const reports: Record<string, ReportFile> = {
  "26.21": report("26.21", "Ahri"),
  "26.20": report("26.20", "Kai'Sa"),
  "26.19": report("26.19", "Ahri", { verdict: "fall", confidence: "low", previous: null }),
};

function renderHistory(entity: string) {
  vi.mocked(fetchIndex).mockResolvedValue(index);
  vi.mocked(fetchReport).mockImplementation(async (_game, patch) => reports[patch]);
  return render(
    <MemoryRouter initialEntries={[`/lol/champion/${encodeURIComponent(entity)}`]}>
      <Routes>
        <Route path="/:game/:entityType/:entity" element={<EntityHistory />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("EntityHistory lists only patches that changed the entity, newest first", async () => {
  renderHistory("Ahri");
  const rows = await screen.findAllByRole("listitem");
  expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining("26.21"), expect.stringContaining("26.19")]);
  expect(screen.getByRole("heading", { level: 1, name: "Ahri" })).toBeInTheDocument();
});

test("EntityHistory rows show changes, verdict, confidence and previous stats", async () => {
  renderHistory("Ahri");
  const [newest, oldest] = await screen.findAllByRole("listitem");
  expect(within(newest).getByText("40 → 45")).toBeInTheDocument();
  expect(newest).toHaveTextContent("Rise");
  expect(newest).toHaveTextContent("medium confidence");
  expect(newest).toHaveTextContent("tier B");
  expect(newest).toHaveTextContent("48.5%");
  expect(within(newest).getByRole("link", { name: /26\.21/ })).toHaveAttribute("href", "/lol/26.21");
  expect(within(oldest).getByText("— → 45")).toBeInTheDocument();
  expect(oldest).toHaveTextContent("Fall");
  expect(oldest).toHaveTextContent("no stats");
  expect(oldest).not.toHaveTextContent("null");
});

test("EntityHistory shows empty message", async () => {
  renderHistory("Zed");
  expect(await screen.findByText("No published patch changed Zed.")).toBeInTheDocument();
});

test("EntityHistory shows the load error", async () => {
  vi.mocked(fetchIndex).mockRejectedValue(new Error("could not load data/index.json"));
  render(
    <MemoryRouter initialEntries={["/lol/champion/Ahri"]}>
      <Routes>
        <Route path="/:game/:entityType/:entity" element={<EntityHistory />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText("could not load data/index.json")).toBeInTheDocument();
});
