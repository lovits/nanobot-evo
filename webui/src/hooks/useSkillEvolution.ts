import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  ApiError,
  compareEvolutionVersions,
  decideEvolutionProposal,
  fetchEvolutionOverview,
  fetchEvolutionSkillDetail,
  requestEvolutionReview,
  restoreEvolutionSkill,
  switchEvolutionVersion,
  updateEvolutionConfig,
} from "@/lib/api";
import type {
  EvolutionOverview,
  EvolutionSkillDetail,
  EvolutionVersionDiff,
} from "@/lib/types";
import { useClient } from "@/providers/ClientProvider";

const REVIEW_POLL_MS = 2_000;

export function useSkillEvolution(open: boolean) {
  const { token } = useClient();
  const { t } = useTranslation();
  const mounted = useRef(true);
  const [overview, setOverview] = useState<EvolutionOverview | null>(null);
  const [detail, setDetail] = useState<EvolutionSkillDetail | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const loadOverview = useCallback(async () => {
    const next = await fetchEvolutionOverview(token);
    if (!mounted.current) return next;
    setOverview(next);
    setSelectedName((current) => {
      if (current && next.skills.some((skill) => skill.name === current)) return current;
      return (
        next.skills.find((skill) => skill.evolvable)?.name
        ?? next.skills[0]?.name
        ?? null
      );
    });
    return next;
  }, [token]);

  const loadDetail = useCallback(async (name: string) => {
    const next = await fetchEvolutionSkillDetail(token, name);
    if (mounted.current) setDetail(next);
    return next;
  }, [token]);

  const refresh = useCallback(async (name: string | null = selectedName) => {
    const nextOverview = await loadOverview();
    const target = (
      name && nextOverview.skills.some((skill) => skill.name === name)
        ? name
        : nextOverview.skills.find((skill) => skill.evolvable)?.name
          ?? nextOverview.skills[0]?.name
          ?? null
    );
    if (target) await loadDetail(target);
  }, [loadDetail, loadOverview, selectedName]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadOverview()
      .catch((reason) => {
        if (!cancelled) setError(errorMessage(reason, t));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadOverview, open]);

  useEffect(() => {
    if (!open || !selectedName) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setError(null);
    loadDetail(selectedName)
      .catch((reason) => {
        if (!cancelled) setError(errorMessage(reason, t));
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadDetail, open, selectedName]);

  useEffect(() => {
    if (!open || !selectedName || !detail?.skill.review_running) return;
    const timer = window.setInterval(() => {
      refresh(selectedName).catch((reason) => {
        if (mounted.current) setError(errorMessage(reason, t));
      });
    }, REVIEW_POLL_MS);
    return () => window.clearInterval(timer);
  }, [detail?.skill.review_running, open, refresh, selectedName, t]);

  const perform = useCallback(async (
    action: string,
    successMessage: string,
    operation: () => Promise<unknown>,
    name: string | null = selectedName,
  ) => {
    setBusyAction(action);
    setError(null);
    setMessage(null);
    try {
      await operation();
      await refresh(name);
      if (mounted.current) setMessage(successMessage);
    } catch (reason) {
      if (mounted.current) setError(errorMessage(reason, t));
    } finally {
      if (mounted.current) setBusyAction(null);
    }
  }, [refresh, selectedName, t]);

  const saveConfig = useCallback(
    (
      enabled: boolean,
      reviewEveryNTrajectories: number,
      reviewModelPreset: string | null,
    ) => perform(
      "config",
      t("settings.skills.evolution.messages.configSaved"),
      () => updateEvolutionConfig(token, {
        enabled,
        review_every_n_trajectories: reviewEveryNTrajectories,
        review_model_preset: reviewModelPreset,
      }),
    ),
    [perform, t, token],
  );

  const requestReview = useCallback(
    (name: string, feedback: string) => perform(
      `review:${name}`,
      t("settings.skills.evolution.messages.reviewRequested"),
      () => requestEvolutionReview(token, name, feedback),
      name,
    ),
    [perform, t, token],
  );

  const approveProposal = useCallback(
    (proposalId: string, skillName: string) => perform(
      `approve:${proposalId}`,
      t("settings.skills.evolution.messages.proposalApplied"),
      () => decideEvolutionProposal(token, proposalId, "approve"),
      skillName,
    ),
    [perform, t, token],
  );

  const rejectProposal = useCallback(
    (proposalId: string, skillName: string) => perform(
      `reject:${proposalId}`,
      t("settings.skills.evolution.messages.proposalRejected"),
      () => decideEvolutionProposal(token, proposalId, "reject"),
      skillName,
    ),
    [perform, t, token],
  );

  const restoreSkill = useCallback(
    (name: string) => perform(
      `restore:${name}`,
      t("settings.skills.evolution.messages.versionRestored"),
      () => restoreEvolutionSkill(token, name),
      name,
    ),
    [perform, t, token],
  );

  const compareVersions = useCallback(
    (
      name: string,
      baseHash: string,
      targetHash: string,
    ): Promise<EvolutionVersionDiff> => (
      compareEvolutionVersions(token, name, baseHash, targetHash)
    ),
    [token],
  );

  const switchVersion = useCallback(
    (name: string, contentHash: string) => perform(
      `switch:${name}`,
      t("settings.skills.evolution.messages.versionSwitched"),
      () => switchEvolutionVersion(token, name, contentHash),
      name,
    ),
    [perform, t, token],
  );

  return {
    overview,
    detail,
    selectedName,
    setSelectedName,
    loading,
    detailLoading,
    busyAction,
    error,
    message,
    refresh,
    saveConfig,
    requestReview,
    approveProposal,
    rejectProposal,
    restoreSkill,
    compareVersions,
    switchVersion,
  };
}

function errorMessage(
  reason: unknown,
  t: ReturnType<typeof useTranslation>["t"],
): string {
  if (reason instanceof ApiError) {
    try {
      const payload = JSON.parse(reason.message) as {
        error?: { code?: string; message?: string };
      };
      const message = payload.error?.message || reason.message;
      return payload.error?.code
        ? t(`settings.skills.evolution.errors.${payload.error.code}`, {
          defaultValue: message,
        })
        : message;
    } catch {
      return reason.message;
    }
  }
  return reason instanceof Error
    ? reason.message
    : t("settings.skills.evolution.errors.requestFailed");
}
