import {
  CheckCircle2,
  CircleAlert,
  GitCompare,
  History,
  Loader2,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { DiffSyntaxHighlight } from "@/components/thread/activity/DiffSyntaxHighlight";
import { parseUnifiedDiffText } from "@/lib/file-diff";
import type {
  EvolutionEvidenceGates,
  EvolutionProposal,
  EvolutionReviewResult,
  EvolutionSkillDetail,
  EvolutionVersionDiff,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type EvolutionTab = "overview" | "proposal" | "versions";

interface SkillEvolutionPanelProps {
  detail: EvolutionSkillDetail | null;
  loading: boolean;
  runtimeActive: boolean;
  busyAction: string | null;
  onReview: (name: string, feedback: string) => Promise<void>;
  onApprove: (proposalId: string, skillName: string) => Promise<void>;
  onReject: (proposalId: string, skillName: string) => Promise<void>;
  onCompareVersions: (
    name: string,
    baseHash: string,
    targetHash: string,
  ) => Promise<EvolutionVersionDiff>;
  onSwitchVersion: (name: string, contentHash: string) => Promise<void>;
}

export function SkillEvolutionPanel({
  detail,
  loading,
  runtimeActive,
  busyAction,
  onReview,
  onApprove,
  onReject,
  onCompareVersions,
  onSwitchVersion,
}: SkillEvolutionPanelProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<EvolutionTab>("overview");
  const [feedback, setFeedback] = useState("");
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setTab("overview");
    setFeedback("");
  }, [detail?.skill.name]);

  if (loading && !detail) {
    return (
      <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        {t("settings.skills.evolution.panel.loading")}
      </div>
    );
  }
  if (!detail) {
    return (
      <div className="flex min-h-56 items-center justify-center px-6 text-center text-sm text-muted-foreground">
        {t("settings.skills.evolution.panel.select")}
      </div>
    );
  }

  const { skill, pending_proposal: proposal } = detail;
  const selectTab = (next: EvolutionTab) => {
    setTab(next);
    panelRef.current?.parentElement?.scrollTo({ top: 0 });
  };
  const tabs: Array<{ id: EvolutionTab; label: string }> = [
    { id: "overview", label: t("settings.skills.evolution.tabs.overview") },
    {
      id: "proposal",
      label: proposal
        ? t("settings.skills.evolution.tabs.proposalCount", { count: 1 })
        : t("settings.skills.evolution.tabs.proposal"),
    },
    {
      id: "versions",
      label: detail.versions.length
        ? t("settings.skills.evolution.tabs.versionsCount", {
          count: detail.versions.length,
        })
        : t("settings.skills.evolution.tabs.versions"),
    },
  ];

  return (
    <div ref={panelRef} className="min-w-0">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-[18px] font-semibold text-foreground">{skill.name}</h3>
          <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-muted-foreground">
            {skill.description}
          </p>
        </div>
        <StatePill state={skill.state} />
      </div>

      <TabList tabs={tabs} active={tab} onChange={selectTab} />

      <div className="mt-5">
        {tab === "overview" ? (
          <OverviewTab
            detail={detail}
            feedback={feedback}
            onFeedbackChange={setFeedback}
            runtimeActive={runtimeActive}
            busy={busyAction === `review:${skill.name}`}
            onReview={() => onReview(skill.name, feedback)}
          />
        ) : null}
        {tab === "proposal" ? (
          <ProposalTab
            proposal={proposal}
            skillName={skill.name}
            busyAction={busyAction}
            onApprove={onApprove}
            onReject={onReject}
          />
        ) : null}
        {tab === "versions" ? (
          <VersionsTab
            detail={detail}
            busy={busyAction === `switch:${skill.name}`}
            onCompare={(baseHash, targetHash) => (
              onCompareVersions(skill.name, baseHash, targetHash)
            )}
            onSwitch={(contentHash) => onSwitchVersion(skill.name, contentHash)}
          />
        ) : null}
      </div>
    </div>
  );
}

function OverviewTab({
  detail,
  feedback,
  onFeedbackChange,
  runtimeActive,
  busy,
  onReview,
}: {
  detail: EvolutionSkillDetail;
  feedback: string;
  onFeedbackChange: (value: string) => void;
  runtimeActive: boolean;
  busy: boolean;
  onReview: () => Promise<void>;
}) {
  const { t, i18n } = useTranslation();
  const { skill } = detail;
  if (!skill.evolvable) {
    return (
      <StatusBox
        icon={<LockKeyhole className="h-5 w-5" aria-hidden />}
        title={t("settings.skills.evolution.protected.title")}
      >
        {t("settings.skills.evolution.protected.description")}
      </StatusBox>
    );
  }

  const progress = Math.min(skill.trajectory_count, skill.review_threshold);
  const progressPercent = skill.review_threshold
    ? Math.round((progress / skill.review_threshold) * 100)
    : 0;
  const hasFeedback = feedback.trim().length > 0;
  const thresholdReached = progress >= skill.review_threshold;
  const cannotReview = (
    !runtimeActive
    || skill.review_running
    || detail.evidence.length === 0
    || (!hasFeedback && !thresholdReached)
    || busy
  );

  return (
    <div className="space-y-6">
      <section aria-labelledby="evolution-progress-title">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h4 id="evolution-progress-title" className="text-[13px] font-medium text-foreground">
              {t("settings.skills.evolution.progress.title")}
            </h4>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {skill.remaining_trajectories > 0
                ? t("settings.skills.evolution.progress.remaining", {
                  count: skill.remaining_trajectories,
                })
                : t("settings.skills.evolution.progress.ready")}
            </p>
          </div>
          <span className="shrink-0 text-[13px] font-medium text-foreground">
            {progress} / {skill.review_threshold}
          </span>
        </div>
        <div
          role="progressbar"
          aria-label={t("settings.skills.evolution.progress.aria")}
          aria-valuemin={0}
          aria-valuemax={skill.review_threshold}
          aria-valuenow={progress}
          className="mt-3 h-2 overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-300 motion-reduce:transition-none"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </section>

      <section>
        <label htmlFor="evolution-feedback" className="text-[13px] font-medium text-foreground">
          {t("settings.skills.evolution.review.title")}
        </label>
        <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
          {t("settings.skills.evolution.review.help")}
        </p>
        <Textarea
          id="evolution-feedback"
          value={feedback}
          onChange={(event) => onFeedbackChange(event.target.value)}
          placeholder={t("settings.skills.evolution.review.placeholder")}
          className="mt-3 min-h-24 resize-y"
          disabled={busy}
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-[12px] text-muted-foreground">
            {!runtimeActive
              ? t("settings.skills.evolution.review.runtimeRequired")
              : detail.evidence.length === 0
                ? t("settings.skills.evolution.review.evidenceRequired")
                : skill.review_running
                  ? t("settings.skills.evolution.review.alreadyRunning")
                  : hasFeedback
                    ? t("settings.skills.evolution.review.feedbackAvailable", {
                      count: detail.evidence.length,
                    })
                    : thresholdReached
                      ? t("settings.skills.evolution.review.thresholdAvailable")
                      : t("settings.skills.evolution.review.thresholdRequired", {
                        count: skill.remaining_trajectories,
                      })}
          </p>
          <Button
            type="button"
            size="sm"
            disabled={cannotReview}
            onClick={() => void onReview()}
          >
            {busy || skill.review_running ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
            )}
            {t("settings.skills.evolution.review.request")}
          </Button>
        </div>
      </section>

      {detail.latest_review && !skill.review_running ? (
        <ReviewResult result={detail.latest_review} />
      ) : null}

      <section>
        <h4 className="text-[13px] font-medium text-foreground">
          {t("settings.skills.evolution.evidence.recent")}
        </h4>
        {detail.evidence.length ? (
          <div className="mt-3 space-y-2">
            {detail.evidence.map((item) => (
              <article
                key={item.trace_id}
                className="rounded-[14px] border border-border/45 bg-muted/20 px-3 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="line-clamp-2 text-[12px] leading-5 text-foreground/85">
                    {item.task_excerpt}
                  </p>
                  {item.objective_failure ? (
                    <CircleAlert
                      className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
                      aria-label={t("settings.skills.evolution.evidence.objectiveFailure")}
                    />
                  ) : (
                    <CheckCircle2
                      className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-300"
                      aria-label={t("settings.skills.evolution.evidence.completed")}
                    />
                  )}
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  {t("settings.skills.evolution.evidence.metadata", {
                    tools: item.tool_calls,
                    errors: item.tool_errors,
                    date: formatDate(item.created_at, i18n.language),
                  })}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-[13px] text-muted-foreground">
            {t("settings.skills.evolution.evidence.empty")}
          </p>
        )}
      </section>
    </div>
  );
}

function ReviewResult({ result }: { result: EvolutionReviewResult }) {
  const { t, i18n } = useTranslation();
  const decision = result.decision ?? result.status;
  const failed = decision === "failed" || decision === "timed_out";
  const title = decision === "no_change"
    ? t("settings.skills.evolution.result.noChange")
    : decision === "failed"
      ? t("settings.skills.evolution.result.failed")
      : decision === "timed_out"
        ? t("settings.skills.evolution.result.timedOut")
        : decision === "propose_patch"
          ? t("settings.skills.evolution.result.proposal")
          : t("settings.skills.evolution.result.running");
  const fallbackReason = decision === "no_change"
    ? t("settings.skills.evolution.result.noChangeReason")
    : decision === "timed_out"
      ? t("settings.skills.evolution.result.timedOutReason")
      : t("settings.skills.evolution.result.failedReason");

  return (
    <section
      role={failed ? "alert" : "status"}
      className={cn(
        "rounded-[14px] border px-3 py-3",
        failed
          ? "border-destructive/30 bg-destructive/5"
          : "border-border/55 bg-muted/20",
      )}
    >
      <div className="flex items-start gap-2.5">
        {failed ? (
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
        ) : (
          <CheckCircle2
            className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-300"
            aria-hidden
          />
        )}
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-foreground">
            {t("settings.skills.evolution.result.title")} · {title}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-[12px] leading-5 text-muted-foreground">
            {result.reason || fallbackReason}
          </p>
          {result.completed_at ? (
            <p className="mt-1 text-[11px] text-muted-foreground/80">
              {formatDate(result.completed_at, i18n.language)}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function ProposalTab({
  proposal,
  skillName,
  busyAction,
  onApprove,
  onReject,
}: {
  proposal: EvolutionProposal | null;
  skillName: string;
  busyAction: string | null;
  onApprove: (proposalId: string, skillName: string) => Promise<void>;
  onReject: (proposalId: string, skillName: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  if (!proposal) {
    return (
      <StatusBox
        icon={<GitCompare className="h-5 w-5" aria-hidden />}
        title={t("settings.skills.evolution.proposal.noneTitle")}
      >
        {t("settings.skills.evolution.proposal.noneDescription")}
      </StatusBox>
    );
  }

  const approving = busyAction === `approve:${proposal.proposal_id}`;
  const rejecting = busyAction === `reject:${proposal.proposal_id}`;
  return (
    <div className="space-y-6">
      <section>
        <h4 className="text-[13px] font-medium text-foreground">
          {t("settings.skills.evolution.proposal.why")}
        </h4>
        <p className="mt-2 text-[13px] leading-6 text-muted-foreground">{proposal.reason}</p>
      </section>

      <section>
        <h4 className="text-[13px] font-medium text-foreground">
          {t("settings.skills.evolution.proposal.gates")}
        </h4>
        <div className="mt-3 space-y-2">
          <GateRows gates={proposal.evidence_gates} />
        </div>
      </section>

      <section>
        <h4 className="text-[13px] font-medium text-foreground">
          {t("settings.skills.evolution.proposal.localReplacement")}
        </h4>
        <div className="mt-3 space-y-2">
          <DiffBlock
            tone="remove"
            label={t("settings.skills.evolution.proposal.before")}
            content={proposal.patch.old_text}
          />
          <DiffBlock
            tone="add"
            label={t("settings.skills.evolution.proposal.after")}
            content={proposal.patch.new_text}
          />
        </div>
      </section>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <ConfirmAction
          title={t("settings.skills.evolution.proposal.rejectTitle")}
          description={t("settings.skills.evolution.proposal.rejectDescription")}
          actionLabel={t("settings.skills.evolution.proposal.rejectAction")}
          triggerLabel={t("settings.skills.evolution.proposal.reject")}
          destructive
          disabled={approving || rejecting}
          busy={rejecting}
          onConfirm={() => onReject(proposal.proposal_id, skillName)}
        />
        <ConfirmAction
          title={t("settings.skills.evolution.proposal.approveTitle")}
          description={t("settings.skills.evolution.proposal.approveDescription")}
          actionLabel={t("settings.skills.evolution.proposal.approveAction")}
          triggerLabel={t("settings.skills.evolution.proposal.approveAction")}
          disabled={approving || rejecting || !proposal.evidence_gates.eligible}
          busy={approving}
          onConfirm={() => onApprove(proposal.proposal_id, skillName)}
        />
      </div>
    </div>
  );
}

function VersionsTab({
  detail,
  busy,
  onCompare,
  onSwitch,
}: {
  detail: EvolutionSkillDetail;
  busy: boolean;
  onCompare: (baseHash: string, targetHash: string) => Promise<EvolutionVersionDiff>;
  onSwitch: (contentHash: string) => Promise<void>;
}) {
  const { t, i18n } = useTranslation();
  const [baseHash, setBaseHash] = useState("");
  const [targetHash, setTargetHash] = useState("");
  const [comparison, setComparison] = useState<EvolutionVersionDiff | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    const current = detail.versions.find((version) => version.is_current);
    const previous = detail.versions.find((version) => !version.is_current);
    setBaseHash(previous?.content_hash ?? current?.content_hash ?? "");
    setTargetHash(current?.content_hash ?? previous?.content_hash ?? "");
    setComparison(null);
    setCompareError(null);
  }, [detail.skill.name, detail.versions]);

  const compare = async () => {
    if (!baseHash || !targetHash) return;
    setComparing(true);
    setCompareError(null);
    try {
      setComparison(await onCompare(baseHash, targetHash));
    } catch (error) {
      setCompareError(error instanceof Error ? error.message : String(error));
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="space-y-5">
      <StatusBox
        icon={<History className="h-5 w-5" aria-hidden />}
        title={t("settings.skills.evolution.versions.current", {
          version: detail.skill.current_version
            ?? t("settings.skills.evolution.versions.unknown"),
        })}
      >
        {t("settings.skills.evolution.versions.description")}
      </StatusBox>

      {detail.versions.length > 1 ? (
        <section className="rounded-[14px] border border-border/45 p-3">
          <h4 className="text-[13px] font-medium text-foreground">
            {t("settings.skills.evolution.versions.compareTitle")}
          </h4>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-end">
            <VersionSelect
              label={t("settings.skills.evolution.versions.baseVersion")}
              value={baseHash}
              versions={detail.versions}
              onChange={setBaseHash}
            />
            <span className="hidden pb-2 text-muted-foreground sm:block" aria-hidden>→</span>
            <VersionSelect
              label={t("settings.skills.evolution.versions.targetVersion")}
              value={targetHash}
              versions={detail.versions}
              onChange={setTargetHash}
            />
          </div>
          <div className="mt-3 flex justify-end">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={comparing || baseHash === targetHash}
              onClick={() => void compare()}
            >
              {comparing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
              {t("settings.skills.evolution.versions.compareAction")}
            </Button>
          </div>
          {compareError ? (
            <p role="alert" className="mt-3 text-[12px] text-destructive">{compareError}</p>
          ) : null}
          {comparison ? <VersionDiffView comparison={comparison} /> : null}
        </section>
      ) : null}

      {detail.versions.length ? (
        <div className="space-y-2">
          {detail.versions.map((version) => (
            <div
              key={`${version.proposal_id}:${version.content_hash}`}
              className="flex items-center justify-between gap-3 rounded-[14px] border border-border/45 px-3 py-3"
            >
              <div className="min-w-0">
                <p className="truncate font-mono text-[12px] text-foreground">
                  {version.content_hash.slice(0, 12)}
                </p>
                {version.created_at ? (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {formatDate(version.created_at, i18n.language)} · {version.proposal_id}
                  </p>
                ) : null}
              </div>
              {version.is_current ? (
                <span className="shrink-0 rounded-full bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
                  {t("settings.skills.evolution.versions.currentLabel")}
                </span>
              ) : (
                <ConfirmAction
                  title={t("settings.skills.evolution.versions.switchTitle")}
                  description={t("settings.skills.evolution.versions.switchDescription")}
                  actionLabel={t("settings.skills.evolution.versions.switchAction")}
                  triggerLabel={t("settings.skills.evolution.versions.switchAction")}
                  disabled={busy}
                  busy={busy}
                  onConfirm={() => onSwitch(version.content_hash)}
                />
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[13px] text-muted-foreground">
          {t("settings.skills.evolution.versions.empty")}
        </p>
      )}

    </div>
  );
}

function VersionDiffView({ comparison }: { comparison: EvolutionVersionDiff }) {
  const { t } = useTranslation();
  const parsed = parseUnifiedDiffText(comparison.diff);
  const lines = parsed.hunks.flatMap((hunk) => hunk.lines);
  const additions = lines.filter((line) => line.kind === "add").length;
  const deletions = lines.filter((line) => line.kind === "delete").length;

  if (!parsed.hunks.length) {
    return (
      <div className="mt-3 rounded-[12px] border border-border/45 bg-muted/25 px-3 py-6 text-center text-[12px] text-muted-foreground">
        {t("settings.skills.evolution.versions.noDiff")}
      </div>
    );
  }

  return (
    <div
      className="mt-3 overflow-hidden rounded-[12px] border border-border/55 bg-background"
      data-testid="version-diff-viewer"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/45 bg-muted/35 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2 font-mono text-[11px] text-muted-foreground">
          <GitCompare className="h-4 w-4 shrink-0" aria-hidden />
          <span className="truncate">{comparison.base_hash.slice(0, 12)}</span>
          <span aria-hidden>→</span>
          <span className="truncate text-foreground">{comparison.target_hash.slice(0, 12)}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-[11px]">
          <span className="text-emerald-600 dark:text-emerald-300">+{additions}</span>
          <span className="text-rose-600 dark:text-rose-300">−{deletions}</span>
        </div>
      </div>
      <div className="max-h-[28rem] overflow-auto [scrollbar-width:auto] [&::-webkit-scrollbar]:h-4 [&::-webkit-scrollbar]:w-4 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/45 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-muted/25">
        {parsed.hunks.map((hunk, index) => (
          <div key={`${hunk.old_start}:${hunk.new_start}:${index}`}>
            <div className="border-b border-border/35 bg-muted/20 px-3 py-1.5 font-mono text-[10px] text-muted-foreground">
              @@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@
            </div>
            <DiffSyntaxHighlight language="markdown" lines={hunk.lines} />
          </div>
        ))}
      </div>
    </div>
  );
}

function VersionSelect({
  label,
  value,
  versions,
  onChange,
}: {
  label: string;
  value: string;
  versions: EvolutionSkillDetail["versions"];
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <label className="min-w-0 text-[12px] text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 h-10 w-full rounded-md border border-input bg-background px-3 font-mono text-[12px] text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {versions.map((version) => (
          <option key={version.content_hash} value={version.content_hash}>
            {version.content_hash.slice(0, 12)}
            {version.is_current ? ` · ${t("settings.skills.evolution.versions.currentLabel")}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

function TabList({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ id: EvolutionTab; label: string }>;
  active: EvolutionTab;
  onChange: (tab: EvolutionTab) => void;
}) {
  const { t } = useTranslation();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKeyDown = (index: number, event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = (index + direction + tabs.length) % tabs.length;
    onChange(tabs[next].id);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={t("settings.skills.evolution.tabs.aria")}
      className="mt-5 flex gap-1 border-b border-border/45"
    >
      {tabs.map((item, index) => (
        <button
          key={item.id}
          ref={(node) => {
            refs.current[index] = node;
          }}
          type="button"
          role="tab"
          aria-selected={active === item.id}
          tabIndex={active === item.id ? 0 : -1}
          onClick={() => onChange(item.id)}
          onKeyDown={(event) => onKeyDown(index, event)}
          className={cn(
            "min-h-11 border-b-2 px-3 text-[13px] font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            active === item.id
              ? "border-foreground text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function GateRows({ gates }: { gates: EvolutionEvidenceGates }) {
  const { t } = useTranslation();
  return (
    <GateRow
      met={gates.eligible}
      label={t("settings.skills.evolution.gates.policySatisfied")}
    />
  );
}

function GateRow({ met, label }: { met: boolean; label: string }) {
  const Icon = met ? CheckCircle2 : CircleAlert;
  return (
    <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
      <Icon
        className={cn(
          "h-4 w-4 shrink-0",
          met ? "text-emerald-600 dark:text-emerald-300" : "text-amber-600 dark:text-amber-300",
        )}
        aria-hidden
      />
      {label}
    </div>
  );
}

function DiffBlock({
  tone,
  label,
  content,
}: {
  tone: "remove" | "add";
  label: string;
  content: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[14px] border",
        tone === "remove"
          ? "border-destructive/25 bg-destructive/5"
          : "border-emerald-500/25 bg-emerald-500/5",
      )}
    >
      <div className="border-b border-border/35 px-3 py-2 text-[11px] font-medium text-muted-foreground">
        {tone === "remove" ? "−" : "+"} {label}
      </div>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words px-3 py-3 font-mono text-[12px] leading-5 text-foreground/80">
        {content}
      </pre>
    </div>
  );
}

function StatusBox({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="flex gap-3 rounded-[16px] border border-border/45 bg-muted/20 px-4 py-4">
      <div className="mt-0.5 text-muted-foreground">{icon}</div>
      <div>
        <h4 className="text-[13px] font-medium text-foreground">{title}</h4>
        <p className="mt-1 text-[12px] leading-5 text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

function StatePill({ state }: { state: EvolutionSkillDetail["skill"]["state"] }) {
  const { t } = useTranslation();
  const label = t(`settings.skills.evolution.states.${state}`);
  const Icon = state === "protected" ? ShieldCheck : state === "reviewing" ? Loader2 : null;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium",
        state === "conflict"
          ? "bg-destructive/10 text-destructive"
          : state === "proposal_pending"
            ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
            : state === "updated"
              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              : "bg-muted text-muted-foreground",
      )}
    >
      {Icon ? (
        <Icon
          className={cn("h-3.5 w-3.5", state === "reviewing" && "animate-spin")}
          aria-hidden
        />
      ) : null}
      {label}
    </span>
  );
}

function ConfirmAction({
  title,
  description,
  actionLabel,
  triggerLabel,
  disabled,
  busy,
  destructive = false,
  onConfirm,
}: {
  title: string;
  description: string;
  actionLabel: string;
  triggerLabel: string;
  disabled: boolean;
  busy: boolean;
  destructive?: boolean;
  onConfirm: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <Button
        type="button"
        variant={destructive ? "destructive" : "default"}
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
        {triggerLabel}
      </Button>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>
            {t("settings.skills.evolution.dialogs.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            className={cn(
              destructive
                && "bg-destructive text-destructive-foreground hover:bg-destructive/90",
            )}
            onClick={() => void onConfirm()}
          >
            {actionLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function formatDate(value: string, locale: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale);
}
