import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SkillsCatalogSettings } from "@/components/settings/SkillsCatalogSettings";
import {
  compareEvolutionVersions,
  decideEvolutionProposal,
  fetchEvolutionOverview,
  fetchEvolutionSkillDetail,
  requestEvolutionReview,
  switchEvolutionVersion,
  updateEvolutionConfig,
} from "@/lib/api";
import type {
  EvolutionOverview,
  EvolutionSkillDetail,
  SkillSummary,
} from "@/lib/types";
import { useSkillEvolution } from "@/hooks/useSkillEvolution";
import { ClientProvider } from "@/providers/ClientProvider";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    decideEvolutionProposal: vi.fn(),
    compareEvolutionVersions: vi.fn(),
    fetchEvolutionOverview: vi.fn(),
    fetchEvolutionSkillDetail: vi.fn(),
    requestEvolutionReview: vi.fn(),
    switchEvolutionVersion: vi.fn(),
    updateEvolutionConfig: vi.fn(),
  };
});

const catalogSkills: SkillSummary[] = [
  {
    name: "repo-analysis",
    description: "Analyze Python repositories.",
    source: "workspace",
    available: true,
  },
  {
    name: "github",
    description: "Built-in GitHub operations.",
    source: "builtin",
    available: true,
  },
];

function overview(): EvolutionOverview {
  return {
    schema_version: 1,
    enabled: true,
    runtime_active: true,
    restart_required: false,
    review_every_n_trajectories: 10,
    review_interval_options: [5, 10, 20, 100],
    review_model_preset: "free",
    review_model_presets: ["free", "default"],
    summary: {
      total: 2,
      evolvable: 1,
      protected: 1,
      reviewing: 0,
      pending_proposals: 1,
    },
    skills: [
      {
        name: "repo-analysis",
        description: "Analyze Python repositories.",
        source: "workspace",
        available: true,
        evolvable: true,
        protection_reason: null,
        state: "proposal_pending",
        trajectory_count: 7,
        review_threshold: 10,
        remaining_trajectories: 3,
        review_running: false,
        last_reviewed_at: "2026-07-26T10:00:00Z",
        last_decision: "proposal_created",
        pending_proposal_count: 1,
        current_version: "current-hash",
      },
      {
        name: "github",
        description: "Built-in GitHub operations.",
        source: "builtin",
        available: true,
        evolvable: false,
        protection_reason: "Built-in Skills are permanently read-only.",
        state: "protected",
        trajectory_count: 0,
        review_threshold: 10,
        remaining_trajectories: 10,
        review_running: false,
        last_reviewed_at: null,
        last_decision: null,
        pending_proposal_count: 0,
        current_version: null,
      },
    ],
  };
}

function detail(): EvolutionSkillDetail {
  return {
    skill: {
      ...overview().skills[0],
      backup_available: true,
    },
    evidence: [
      {
        trace_id: "trace-1",
        created_at: "2026-07-26T09:00:00Z",
        turn_id: "turn-1",
        project_scope_hash: "project-1",
        task_excerpt:
          "Inspect a Python package and summarize its architecture.",
        tool_calls: 5,
        tool_errors: 1,
        iterations: 3,
        objective_failure: false,
        stop_reason: "completed",
      },
    ],
    latest_review: null,
    pending_proposal: {
      proposal_id: "proposal-1",
      skill_name: "repo-analysis",
      reason: "Repeated traces show that dependency inspection is missing.",
      status: "pending",
      created_at: "2026-07-26T10:00:00Z",
      base_hash: "current-hash",
      evidence_trace_ids: ["trace-1"],
      patch: {
        old_text: "Inspect Python files.",
        new_text: "Inspect Python files and dependency metadata.",
      },
      evidence_gates: {
        trace_count: 3,
        eligible: true,
      },
    },
    versions: [
      {
        content_hash: "b".repeat(64),
        proposal_id: "current",
        created_at: "",
        is_current: true,
      },
      {
        content_hash: "a".repeat(64),
        proposal_id: "proposal-0",
        created_at: "2026-07-25T10:00:00Z",
        is_current: false,
      },
    ],
  };
}

function renderCatalog() {
  return render(
    <ClientProvider client={{} as never} token="tok">
      <SkillsCatalogSettings skills={catalogSkills} />
    </ClientProvider>,
  );
}

describe("Skill evolution management", () => {
  beforeEach(() => {
    vi.mocked(fetchEvolutionOverview).mockResolvedValue(overview());
    vi.mocked(fetchEvolutionSkillDetail).mockImplementation(
      async (_token, name) =>
        name === "repo-analysis"
          ? detail()
          : {
              ...detail(),
              skill: {
                ...overview().skills[1],
                backup_available: false,
              },
              evidence: [],
              latest_review: null,
              pending_proposal: null,
              versions: [],
            },
    );
    vi.mocked(decideEvolutionProposal).mockResolvedValue({ ok: true });
    vi.mocked(requestEvolutionReview).mockResolvedValue({
      ok: true,
      review_id: "review-1",
      state: "reviewing",
    });
    vi.mocked(compareEvolutionVersions).mockResolvedValue({
      base_hash: "a".repeat(64),
      target_hash: "b".repeat(64),
      diff: "--- old\n+++ new\n@@ -1 +1 @@\n-old\n+new\n",
    });
    vi.mocked(switchEvolutionVersion).mockResolvedValue({ ok: true });
    vi.mocked(updateEvolutionConfig).mockResolvedValue({ ok: true });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("opens from the existing Skills page and returns focus when closed", async () => {
    const user = userEvent.setup();
    renderCatalog();

    const trigger = screen.getByRole("button", {
      name: "Evolution management",
    });
    await user.click(trigger);

    const title = await screen.findByRole("heading", {
      name: "Skill evolution management",
    });
    expect(title).toHaveFocus();
    expect(await screen.findByText("7 / 10")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "Automatic review progress" }),
    ).toHaveAttribute("aria-valuenow", "7");

    await user.click(screen.getByRole("button", { name: /^github/ }));
    expect(
      await screen.findByText("Protected built-in Skill"),
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("renders the evolution management surface in Simplified Chinese", async () => {
    await act(async () => {
      const { setAppLanguage } = await import("@/i18n");
      await setAppLanguage("zh-CN");
    });

    const user = userEvent.setup();
    renderCatalog();

    await user.click(screen.getByRole("button", { name: "进化管理" }));

    expect(
      await screen.findByRole("heading", { name: "Skills 进化管理" }),
    ).toBeInTheDocument();
    const configPanel = screen.getByTestId("evolution-config-panel");
    const statusPanel = screen.getByTestId("evolution-status-panel");
    expect(within(configPanel).getByText("自动复盘策略")).toBeInTheDocument();
    expect(within(configPanel).getByText("复盘模型预设")).toBeInTheDocument();
    expect(
      within(configPanel).getByRole("button", { name: "保存配置" }),
    ).toBeInTheDocument();
    expect(within(statusPanel).getByText("进化运行时")).toBeInTheDocument();
    expect(within(statusPanel).getByText("可进化")).toBeInTheDocument();
    expect(within(statusPanel).getByText("受保护")).toBeInTheDocument();
    expect(within(statusPanel).getByText("待处理")).toBeInTheDocument();
    expect(screen.getByTestId("evolution-workspace")).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "每使用 5 次复盘" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "概览" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "请求复盘" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "提案 1" }));
    expect(
      screen.getByRole("button", { name: "批准并应用" }),
    ).toBeInTheDocument();
  });

  it("requires feedback before the periodic threshold and shows failed review reasons", async () => {
    await act(async () => {
      const { setAppLanguage } = await import("@/i18n");
      await setAppLanguage("en");
    });
    const failedDetail = detail();
    failedDetail.latest_review = {
      review_id: "review-failed",
      status: "completed",
      trigger: "manual",
      decision: "failed",
      reason: "Provider returned an invalid response",
      requested_at: "2026-07-26T09:00:00Z",
      completed_at: "2026-07-26T09:01:00Z",
    };
    vi.mocked(fetchEvolutionSkillDetail).mockResolvedValue(failedDetail);

    const user = userEvent.setup();
    renderCatalog();
    await user.click(
      screen.getByRole("button", { name: "Evolution management" }),
    );

    const reviewButton = await screen.findByRole("button", {
      name: "Request review",
    });
    expect(reviewButton).toBeDisabled();
    expect(
      screen.getByText(/3 more attributed trajectory record/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Review failed/)).toBeInTheDocument();
    expect(
      screen.getByText("Provider returned an invalid response"),
    ).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText("Describe one concrete Skill issue to verify…"),
      "Dependency guidance is incomplete",
    );
    expect(reviewButton).toBeEnabled();
  });

  it("saves a selected automatic review interval", async () => {
    const user = userEvent.setup();
    renderCatalog();
    await user.click(
      screen.getByRole("button", { name: "Evolution management" }),
    );

    await user.selectOptions(
      await screen.findByLabelText("Automatic review strategy"),
      "20",
    );
    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );

    await waitFor(() => {
      expect(updateEvolutionConfig).toHaveBeenCalledWith("tok", {
        enabled: true,
        review_every_n_trajectories: 20,
        review_model_preset: "free",
      });
    });
  });

  it("requires confirmation before applying a proposal or switching a version", async () => {
    const user = userEvent.setup();
    renderCatalog();
    await user.click(
      screen.getByRole("button", { name: "Evolution management" }),
    );
    await screen.findByText("7 / 10");

    await user.click(screen.getByRole("tab", { name: "Proposal 1" }));
    expect(screen.getByText("Inspect Python files.")).toBeInTheDocument();
    expect(
      screen.getByText("Inspect Python files and dependency metadata."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve and apply" }));
    const approveDialog = await screen.findByRole("alertdialog");
    await user.click(
      within(approveDialog).getByRole("button", { name: "Approve and apply" }),
    );
    await waitFor(() => {
      expect(decideEvolutionProposal).toHaveBeenCalledWith(
        "tok",
        "proposal-1",
        "approve",
      );
    });

    await user.click(screen.getByRole("tab", { name: "Versions 2" }));
    await user.click(screen.getByRole("button", { name: "Compare versions" }));
    expect(
      await screen.findByTestId("version-diff-viewer"),
    ).toBeInTheDocument();
    expect(screen.getByText("old")).toBeInTheDocument();
    expect(screen.getByText("new")).toBeInTheDocument();
    expect(compareEvolutionVersions).toHaveBeenCalledWith(
      "tok",
      "repo-analysis",
      "a".repeat(64),
      "b".repeat(64),
    );

    await user.click(screen.getByRole("button", { name: "Switch version" }));
    const switchDialog = await screen.findByRole("alertdialog");
    await user.click(
      within(switchDialog).getByRole("button", {
        name: "Switch version",
      }),
    );
    await waitFor(() => {
      expect(switchEvolutionVersion).toHaveBeenCalledWith(
        "tok",
        "repo-analysis",
        "a".repeat(64),
      );
    });
  });

  it("polls only while a Skill review is running", async () => {
    const reviewingOverview = overview();
    reviewingOverview.skills[0] = {
      ...reviewingOverview.skills[0],
      state: "reviewing",
      review_running: true,
    };
    reviewingOverview.summary.reviewing = 1;
    const reviewingDetail = detail();
    reviewingDetail.skill = {
      ...reviewingDetail.skill,
      state: "reviewing",
      review_running: true,
    };
    const completedDetail = detail();
    completedDetail.skill = {
      ...completedDetail.skill,
      state: "proposal_pending",
      review_running: false,
    };

    vi.mocked(fetchEvolutionOverview).mockResolvedValue(reviewingOverview);
    vi.mocked(fetchEvolutionSkillDetail)
      .mockResolvedValueOnce(reviewingDetail)
      .mockResolvedValue(completedDetail);

    let poll: (() => void) | null = null;
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");
    const setIntervalSpy = vi
      .spyOn(window, "setInterval")
      .mockImplementation((callback) => {
        poll = callback as () => void;
        return 17;
      });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <ClientProvider client={{} as never} token="tok">
        {children}
      </ClientProvider>
    );
    const { result } = renderHook(() => useSkillEvolution(true), { wrapper });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.detail?.skill.review_running).toBe(true);
    expect(poll).not.toBeNull();

    await act(async () => {
      poll?.();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.detail?.skill.review_running).toBe(false);
    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(fetchEvolutionSkillDetail).toHaveBeenCalledTimes(2);
    setIntervalSpy.mockRestore();
    clearIntervalSpy.mockRestore();
  });
});
