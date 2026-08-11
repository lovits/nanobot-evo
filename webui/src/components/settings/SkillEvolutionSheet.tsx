import {
  ArrowLeft,
  BrainCircuit,
  ChevronRight,
  CircleAlert,
  Loader2,
  LockKeyhole,
  Save,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useTranslation } from "react-i18next";

import { SkillEvolutionPanel } from "@/components/settings/SkillEvolutionPanel";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { useSkillEvolution } from "@/hooks/useSkillEvolution";
import type { EvolutionSkillSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

type SkillFilter = "all" | "evolvable" | "pending";

export function SkillEvolutionSheet({
  open,
  onOpenChange,
  returnFocusRef,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  returnFocusRef: RefObject<HTMLButtonElement>;
}) {
  const { t } = useTranslation();
  const evolution = useSkillEvolution(open);
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  const [filter, setFilter] = useState<SkillFilter>("all");
  const [mobileDetail, setMobileDetail] = useState(false);
  const [desiredEnabled, setDesiredEnabled] = useState(false);
  const [desiredReviewThreshold, setDesiredReviewThreshold] = useState(10);
  const [desiredPreset, setDesiredPreset] = useState("");

  useEffect(() => {
    if (!evolution.overview) return;
    setDesiredEnabled(evolution.overview.enabled);
    setDesiredReviewThreshold(evolution.overview.review_every_n_trajectories);
    setDesiredPreset(evolution.overview.review_model_preset ?? "");
  }, [evolution.overview]);

  useEffect(() => {
    if (!open) {
      setMobileDetail(false);
      setFilter("all");
    }
  }, [open]);

  const filteredSkills = useMemo(() => {
    const skills = evolution.overview?.skills ?? [];
    if (filter === "evolvable")
      return skills.filter((skill) => skill.evolvable);
    if (filter === "pending") {
      return skills.filter(
        (skill) => skill.pending_proposal_count > 0 || skill.review_running,
      );
    }
    return skills;
  }, [evolution.overview?.skills, filter]);

  const configChanged = Boolean(
    evolution.overview &&
    (desiredEnabled !== evolution.overview.enabled ||
      desiredReviewThreshold !==
        evolution.overview.review_every_n_trajectories ||
      desiredPreset !== (evolution.overview.review_model_preset ?? "")),
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full max-w-none gap-0 overflow-hidden p-0 sm:max-w-none md:w-[min(72rem,calc(100vw-2rem))]"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          titleRef.current?.focus();
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocusRef.current?.focus();
        }}
      >
        <header className="border-b border-border/45 px-4 py-4 pr-14 sm:px-6">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-muted/70 text-muted-foreground">
              <BrainCircuit className="h-5 w-5" aria-hidden />
            </div>
            <div className="min-w-0">
              <SheetTitle
                ref={titleRef}
                tabIndex={-1}
                className="text-[19px] font-semibold focus:outline-none"
              >
                {t("settings.skills.evolution.title")}
              </SheetTitle>
              <SheetDescription className="mt-1 text-[13px] leading-5">
                {t("settings.skills.evolution.description")}
              </SheetDescription>
            </div>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain md:overflow-hidden">
          <div className="flex h-full min-h-0 flex-col gap-3 px-4 py-4 sm:px-6">
            {evolution.loading && !evolution.overview ? (
              <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                {t("settings.skills.evolution.loading")}
              </div>
            ) : null}

            {evolution.error ? (
              <div
                role="alert"
                className="rounded-[14px] border border-destructive/25 bg-destructive/5 px-3 py-3 text-[13px] text-destructive"
              >
                {evolution.error}
              </div>
            ) : null}
            <div aria-live="polite" aria-atomic="true" className="sr-only">
              {evolution.message}
            </div>

            {evolution.overview ? (
              <>
                <div className="grid shrink-0 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(24rem,0.9fr)]">
                  <EvolutionConfigCard
                    reviewThreshold={desiredReviewThreshold}
                    reviewThresholdOptions={
                      evolution.overview.review_interval_options
                    }
                    onReviewThresholdChange={setDesiredReviewThreshold}
                    preset={desiredPreset}
                    presets={evolution.overview.review_model_presets}
                    onPresetChange={setDesiredPreset}
                    changed={configChanged}
                    saving={evolution.busyAction === "config"}
                    onSave={() =>
                      evolution.saveConfig(
                        desiredEnabled,
                        desiredReviewThreshold,
                        desiredPreset || null,
                      )
                    }
                  />
                  <EvolutionStatusCard
                    enabled={desiredEnabled}
                    onEnabledChange={setDesiredEnabled}
                    runtimeActive={evolution.overview.runtime_active}
                    restartRequired={evolution.overview.restart_required}
                    evolvable={evolution.overview.summary.evolvable}
                    protectedCount={evolution.overview.summary.protected}
                    pending={evolution.overview.summary.pending_proposals}
                  />
                </div>

                <div
                  data-testid="evolution-workspace"
                  className="min-h-[22rem] min-w-0 flex-1 rounded-[16px] border border-border/45 bg-muted/10 p-3 md:min-h-0"
                >
                  <div className="grid h-full min-h-0 min-w-0 gap-4 md:grid-cols-[17rem_minmax(0,1fr)]">
                    <section
                      aria-label={t("settings.skills.evolution.regions.list")}
                      className={cn(
                        mobileDetail ? "hidden" : "block",
                        "min-h-0 md:flex md:flex-col",
                      )}
                    >
                      <FilterTabs value={filter} onChange={setFilter} />
                      <div className="mt-3 min-h-0 space-y-1 md:flex-1 md:overflow-y-auto md:overscroll-contain md:pr-2 [scrollbar-width:auto] [&::-webkit-scrollbar]:w-4 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/45 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-muted/25">
                        {filteredSkills.length ? (
                          filteredSkills.map((skill) => (
                            <SkillListRow
                              key={`${skill.source}:${skill.name}`}
                              skill={skill}
                              selected={skill.name === evolution.selectedName}
                              onSelect={() => {
                                evolution.setSelectedName(skill.name);
                                setMobileDetail(true);
                              }}
                            />
                          ))
                        ) : (
                          <p className="px-3 py-8 text-center text-[13px] text-muted-foreground">
                            {t("settings.skills.evolution.filters.noMatch")}
                          </p>
                        )}
                      </div>
                    </section>

                    <section
                      aria-label={t(
                        "settings.skills.evolution.regions.details",
                      )}
                      className={cn(
                        mobileDetail ? "block" : "hidden",
                        "min-h-0 min-w-0 md:block md:overflow-y-auto md:overscroll-contain md:pr-2 [scrollbar-width:auto] [&::-webkit-scrollbar]:w-4 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/45 [&::-webkit-scrollbar-track]:rounded-full [&::-webkit-scrollbar-track]:bg-muted/25",
                      )}
                    >
                      <button
                        type="button"
                        className="mb-3 flex min-h-11 items-center gap-1 text-[13px] font-medium text-muted-foreground md:hidden"
                        onClick={() => setMobileDetail(false)}
                      >
                        <ArrowLeft className="h-4 w-4" aria-hidden />
                        {t("settings.skills.evolution.backToSkills")}
                      </button>
                      <SkillEvolutionPanel
                        detail={evolution.detail}
                        loading={evolution.detailLoading}
                        runtimeActive={evolution.overview.runtime_active}
                        busyAction={evolution.busyAction}
                        onReview={evolution.requestReview}
                        onApprove={evolution.approveProposal}
                        onReject={evolution.rejectProposal}
                        onCompareVersions={evolution.compareVersions}
                        onSwitchVersion={evolution.switchVersion}
                      />
                    </section>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function EvolutionConfigCard({
  reviewThreshold,
  reviewThresholdOptions,
  onReviewThresholdChange,
  preset,
  presets,
  onPresetChange,
  changed,
  saving,
  onSave,
}: {
  reviewThreshold: number;
  reviewThresholdOptions: number[];
  onReviewThresholdChange: (threshold: number) => void;
  preset: string;
  presets: string[];
  onPresetChange: (preset: string) => void;
  changed: boolean;
  saving: boolean;
  onSave: () => Promise<void>;
}) {
  const { t } = useTranslation();
  return (
    <section
      data-testid="evolution-config-panel"
      className="flex h-full flex-col rounded-[16px] border border-border/45 bg-muted/20 p-3"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="min-w-0 text-[12px] text-muted-foreground">
          {t("settings.skills.evolution.runtime.reviewInterval")}
          <select
            value={reviewThreshold}
            onChange={(event) =>
              onReviewThresholdChange(Number(event.target.value))
            }
            className="mt-1.5 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {reviewThresholdOptions.map((count) => (
              <option key={count} value={count}>
                {t("settings.skills.evolution.runtime.reviewIntervalOption", {
                  count,
                })}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0 flex-1 text-[12px] text-muted-foreground">
          {t("settings.skills.evolution.runtime.modelPreset")}
          <select
            value={preset}
            onChange={(event) => onPresetChange(event.target.value)}
            className="mt-1.5 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">
              {t("settings.skills.evolution.runtime.currentMainModel")}
            </option>
            {presets.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="min-w-0 text-[11px] leading-5 text-muted-foreground">
          {t("settings.skills.evolution.runtime.help")}
        </p>
        <Button
          type="button"
          variant="outline"
          className="shrink-0"
          disabled={!changed || saving}
          onClick={() => void onSave()}
        >
          {saving ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Save className="mr-2 h-4 w-4" aria-hidden />
          )}
          {t("settings.skills.evolution.runtime.save")}
        </Button>
      </div>
    </section>
  );
}

function EvolutionStatusCard({
  enabled,
  onEnabledChange,
  runtimeActive,
  restartRequired,
  evolvable,
  protectedCount,
  pending,
}: {
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  runtimeActive: boolean;
  restartRequired: boolean;
  evolvable: number;
  protectedCount: number;
  pending: number;
}) {
  const { t } = useTranslation();
  return (
    <section
      data-testid="evolution-status-panel"
      className="flex h-full flex-col rounded-[16px] border border-border/45 bg-muted/20 p-3"
    >
      <div className="flex min-h-11 items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h3 className="text-[13px] font-medium text-foreground">
            {t("settings.skills.evolution.runtime.title")}
          </h3>
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <RuntimePill active={enabled}>
              {t(
                enabled
                  ? "settings.skills.evolution.runtime.configEnabled"
                  : "settings.skills.evolution.runtime.configDisabled",
              )}
            </RuntimePill>
            <RuntimePill active={runtimeActive}>
              {t(
                runtimeActive
                  ? "settings.skills.evolution.runtime.runtimeActive"
                  : "settings.skills.evolution.runtime.runtimeInactive",
              )}
            </RuntimePill>
            {restartRequired ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-1 font-medium text-amber-700 dark:text-amber-300">
                <CircleAlert className="h-3.5 w-3.5" aria-hidden />
                {t("settings.skills.evolution.runtime.restartRequired")}
              </span>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label={t("settings.skills.evolution.runtime.enableAria")}
          onClick={() => onEnabledChange(!enabled)}
          className="flex h-11 w-14 shrink-0 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span
            aria-hidden
            className={cn(
              "flex h-6 w-11 items-center rounded-full p-0.5 transition-colors",
              enabled ? "bg-primary" : "bg-muted-foreground/30",
            )}
          >
            <span
              className={cn(
                "h-5 w-5 rounded-full bg-background shadow-sm transition-transform",
                enabled && "translate-x-5",
              )}
            />
          </span>
        </button>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <SummaryMetric
          label={t("settings.skills.evolution.summary.evolvable")}
          value={evolvable}
        />
        <SummaryMetric
          label={t("settings.skills.evolution.summary.protected")}
          value={protectedCount}
        />
        <SummaryMetric
          label={t("settings.skills.evolution.summary.pending")}
          value={pending}
          emphasized={pending > 0}
        />
      </div>
    </section>
  );
}

function FilterTabs({
  value,
  onChange,
}: {
  value: SkillFilter;
  onChange: (value: SkillFilter) => void;
}) {
  const { t } = useTranslation();
  const filters: Array<{ id: SkillFilter; label: string }> = [
    { id: "all", label: t("settings.skills.evolution.filters.all") },
    {
      id: "evolvable",
      label: t("settings.skills.evolution.filters.evolvable"),
    },
    { id: "pending", label: t("settings.skills.evolution.filters.pending") },
  ];
  return (
    <div
      className="flex flex-wrap gap-1"
      aria-label={t("settings.skills.evolution.filters.aria")}
    >
      {filters.map((filter) => (
        <button
          key={filter.id}
          type="button"
          aria-pressed={value === filter.id}
          onClick={() => onChange(filter.id)}
          className={cn(
            "min-h-9 rounded-full px-3 text-[12px] font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            value === filter.id
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:text-foreground",
          )}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}

function SkillListRow({
  skill,
  selected,
  onSelect,
}: {
  skill: EvolutionSkillSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
      className={cn(
        "flex min-h-16 w-full min-w-0 items-center gap-3 rounded-[14px] px-3 py-2.5 text-left",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        selected ? "bg-accent text-accent-foreground" : "hover:bg-muted/50",
      )}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] bg-muted text-muted-foreground">
        {skill.evolvable ? (
          <BrainCircuit className="h-4 w-4" aria-hidden />
        ) : (
          <LockKeyhole className="h-4 w-4" aria-hidden />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-foreground">
          {skill.name}
        </p>
        <p className="mt-1 truncate text-[11px] text-muted-foreground">
          {skillStateLabel(skill, t)}
        </p>
      </div>
      <ChevronRight
        className="h-4 w-4 shrink-0 text-muted-foreground md:hidden"
        aria-hidden
      />
    </button>
  );
}

function SummaryMetric({
  label,
  value,
  emphasized = false,
}: {
  label: string;
  value: number;
  emphasized?: boolean;
}) {
  return (
    <div className="rounded-[12px] border border-border/35 bg-background/45 px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 text-[18px] font-semibold text-foreground",
          emphasized && "text-amber-700 dark:text-amber-300",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function RuntimePill({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-1 font-medium",
        active
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function skillStateLabel(
  skill: EvolutionSkillSummary,
  t: ReturnType<typeof useTranslation>["t"],
): string {
  const prefix = "settings.skills.evolution.skillStates";
  if (skill.state === "protected") return t(`${prefix}.protected`);
  if (skill.state === "reviewing") return t(`${prefix}.reviewing`);
  if (skill.state === "proposal_pending") {
    return t(`${prefix}.proposalPending`, {
      count: skill.pending_proposal_count,
    });
  }
  if (skill.state === "conflict") return t(`${prefix}.conflict`);
  if (skill.state === "updated") return t(`${prefix}.updated`);
  if (skill.state === "unavailable") return t(`${prefix}.unavailable`);
  return t(`${prefix}.collecting`, {
    count: skill.trajectory_count,
    threshold: skill.review_threshold,
  });
}
