import { useEffect, useMemo, useState } from "react";
import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultBadge } from "./Shared";
import * as Icons from "./Icons";




const USAGE_CHART_BASE_COLORS = ["#2563eb", "#f59e0b", "#16a34a", "#ef4444", "#8b5cf6", "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#14b8a6"];
const USAGE_TIMEZONES = {
  IST: { label: "IST", timeZone: "Asia/Kolkata", offsetMinutes: 330 },
  UTC: { label: "UTC", timeZone: "UTC", offsetMinutes: 0 },
};
const MONTH_OPTIONS = [
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];
const RECENT_WINDOW_OPTIONS = [
  { value: "24h", label: "Last 24H", durationMs: 24 * 60 * 60 * 1000 },
  { value: "7d", label: "Last 7D", durationMs: 7 * 24 * 60 * 60 * 1000 },
  { value: "30d", label: "Last 30D", durationMs: 30 * 24 * 60 * 60 * 1000 },
  { value: "all", label: "All", durationMs: null },
];

function titleCase(value) {
  return String(value || "")
    .split(/[\s._/-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getUsageChartColor(index, total) {
  if (index < USAGE_CHART_BASE_COLORS.length) {
    return USAGE_CHART_BASE_COLORS[index];
  }
  const hue = Math.round((index * 137.508) % 360);
  const saturation = total > 6 ? 78 : 72;
  const lightness = 56;
  return `hsl(${hue} ${saturation}% ${lightness}%)`;
}

function formatEntityLabel(kind) {
  const labels = {
    email: "Emails",
    phone: "Phones",
    person: "People",
    organization: "Organizations",
    address: "Addresses",
    passport: "Passports",
    pancard: "PAN Cards",
    blood_group: "Blood Groups",
    ssn: "SSNs",
    card: "Cards",
    dob: "Birth Dates",
    bank_account: "Bank Accounts",
  };
  return labels[kind] || titleCase(kind);
}

function getUsageFeatureMeta(feature) {
  const raw = String(feature || "");
  const requestMatch = raw.match(/^request:([A-Z]+)\s+(.+)$/);
  if (requestMatch) {
    const [, method, path] = requestMatch;
    return {
      key: raw,
      label: `${method} ${path}`,
      endpoint: path,
      technicalLabel: raw,
    };
  }

  const known = {
    "pii.masking": { label: "PII Masking", endpoint: "/v1/pii/mask" },
    "sentinel.shield": { label: "Sentinel Shield", endpoint: "/v1/sentinel/analyze" },
    "engine.security": { label: "Removed Shared Security Route", endpoint: "/v1/engine/security/process" },
    "biomed.masking": { label: "BioMed Masking", endpoint: "/v1/biomed/mask" },
    "lab.execute": { label: "Sandbox Lab", endpoint: "/v1/lab/execute" },
    "playground.run": { label: "Playground", endpoint: "/v1/playground/run" },
    "engine.vault.encrypt": { label: "Vault Encrypt", endpoint: "/v1/engine/security/vault/encrypt" },
    "engine.vault.decrypt": { label: "Vault Decrypt", endpoint: "/v1/engine/security/vault/decrypt" },
    "engine.pandora.transform": { label: "Pandora Data Lab", endpoint: "/v1/engine/pandora/transform" },
  };

  const mapped = known[raw];
  return {
    key: raw,
    label: mapped?.label || titleCase(raw),
    endpoint: mapped?.endpoint || null,
    technicalLabel: raw,
  };
}

function parseUsageTimestamp(value) {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const normalized = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(value) && !/[zZ]|[+-]\d{2}:\d{2}$/.test(value)
      ? `${value.replace(" ", "T")}Z`
      : value;
    return new Date(normalized).getTime();
  }
  return Number.NaN;
}

function formatUsageTimestampLabel(timestamp, totalSpanMs, intervalMs, timezoneMode) {
  const date = new Date(timestamp);
  const timeZone = USAGE_TIMEZONES[timezoneMode]?.timeZone || USAGE_TIMEZONES.IST.timeZone;
  const timeLabel = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone });
  const dayLabel = date.toLocaleDateString([], { month: "short", day: "numeric", timeZone });
  if (intervalMs >= 24 * 60 * 60 * 1000) {
    return dayLabel;
  }
  if (totalSpanMs >= 24 * 60 * 60 * 1000) {
    return `${dayLabel} ${timeLabel}`;
  }
  return timeLabel;
}

function formatUsageRangeLabel(startTimestamp, endTimestamp, timezoneMode) {
  const startDate = new Date(startTimestamp);
  const endDate = new Date(endTimestamp);
  const timeZone = USAGE_TIMEZONES[timezoneMode]?.timeZone || USAGE_TIMEZONES.IST.timeZone;
  const startLabel = startDate.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
  const sameDay = startDate.toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit", timeZone })
    === endDate.toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit", timeZone });
  const endLabel = sameDay
    ? endDate.toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
        timeZone,
      })
    : endDate.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone,
      });
  return `${startLabel} - ${endLabel}`;
}

function getUsageIntervalMs(recentWindow, totalSpanMs) {
  if (recentWindow === "24h") {
    if (totalSpanMs <= 6 * 60 * 60 * 1000) return 30 * 60 * 1000;
    if (totalSpanMs <= 12 * 60 * 60 * 1000) return 60 * 60 * 1000;
    return 2 * 60 * 60 * 1000;
  }
  if (recentWindow === "7d") {
    if (totalSpanMs <= 24 * 60 * 60 * 1000) return 2 * 60 * 60 * 1000;
    if (totalSpanMs <= 3 * 24 * 60 * 60 * 1000) return 6 * 60 * 60 * 1000;
    return 12 * 60 * 60 * 1000;
  }
  if (recentWindow === "30d") {
    if (totalSpanMs <= 24 * 60 * 60 * 1000) return 2 * 60 * 60 * 1000;
    if (totalSpanMs <= 3 * 24 * 60 * 60 * 1000) return 6 * 60 * 60 * 1000;
    if (totalSpanMs <= 10 * 24 * 60 * 60 * 1000) return 12 * 60 * 60 * 1000;
    return 24 * 60 * 60 * 1000;
  }
  if (totalSpanMs <= 3 * 24 * 60 * 60 * 1000) return 6 * 60 * 60 * 1000;
  if (totalSpanMs <= 21 * 24 * 60 * 60 * 1000) return 24 * 60 * 60 * 1000;
  if (totalSpanMs <= 120 * 24 * 60 * 60 * 1000) return 7 * 24 * 60 * 60 * 1000;
  return 30 * 24 * 60 * 60 * 1000;
}

function filterUsageEventsByRecentWindow(events, recentWindow) {
  const activeWindow = RECENT_WINDOW_OPTIONS.find((option) => option.value === recentWindow);
  if (!activeWindow || activeWindow.durationMs == null) return events;
  if (!events.length) return events;

  const latestTimestamp = Math.max(...events.map((event) => event.timestamp));
  const threshold = latestTimestamp - activeWindow.durationMs;
  return events.filter((event) => event.timestamp >= threshold);
}

function buildUsageSeries(events, keyFn, options = {}) {
  const { maxSeries = 4, timezoneMode = "IST", recentWindow = "30d" } = options;
  const orderedEvents = [...(events || [])]
    .map((event) => ({ ...event, timestamp: parseUsageTimestamp(event.created_at) }))
    .filter((event) => Number.isFinite(event.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp);

  if (!orderedEvents.length) {
    return {
      intervals: [],
      series: [],
      minTimestamp: 0,
      maxTimestamp: 0,
      maxValue: 0,
      axisLabels: [],
      totalEvents: 0,
      timezoneMode,
    };
  }

  const totals = new Map();
  for (const event of orderedEvents) {
    const meta = getUsageFeatureMeta(keyFn(event));
    const current = totals.get(meta.key) || { ...meta, units: 0, calls: 0 };
    current.units += Number(event.units || 0);
    current.calls += 1;
    totals.set(meta.key, current);
  }

  const topLabels = Array.from(totals.values())
    .sort((a, b) => b.calls - a.calls || b.units - a.units)
    .slice(0, maxSeries)
    .map((item) => item.key);

  if (!topLabels.length) {
    return {
      intervals: [],
      series: [],
      minTimestamp: 0,
      maxTimestamp: 0,
      maxValue: 0,
      axisLabels: [],
      totalEvents: 0,
      timezoneMode,
    };
  }

  const minTimestamp = orderedEvents[0].timestamp;
  const maxTimestamp = orderedEvents[orderedEvents.length - 1].timestamp;
  const totalSpanMs = Math.max(maxTimestamp - minTimestamp, 60 * 60 * 1000);
  const intervalMs = getUsageIntervalMs(recentWindow, totalSpanMs);
  const offsetMs = (USAGE_TIMEZONES[timezoneMode]?.offsetMinutes || 0) * 60 * 1000;
  const alignedStart = Math.floor((minTimestamp + offsetMs) / intervalMs) * intervalMs - offsetMs;
  const alignedEnd = Math.ceil((maxTimestamp + offsetMs) / intervalMs) * intervalMs - offsetMs;
  const intervalCount = Math.max(1, Math.round((alignedEnd - alignedStart) / intervalMs) + 1);
  const intervals = Array.from({ length: intervalCount }, (_, index) => {
    const start = alignedStart + index * intervalMs;
    const end = start + intervalMs;
    return {
      key: `${start}-${end}`,
      start,
      end,
      label: formatUsageTimestampLabel(start, totalSpanMs, intervalMs, timezoneMode),
      rangeLabel: formatUsageRangeLabel(start, end, timezoneMode),
      values: new Map(topLabels.map((item) => [item, { calls: 0, units: 0 }])),
    };
  });

  for (const event of orderedEvents) {
    const label = keyFn(event);
    if (!topLabels.includes(label)) continue;
    const index = Math.min(intervals.length - 1, Math.max(0, Math.floor((event.timestamp - alignedStart) / intervalMs)));
    const current = intervals[index].values.get(label) || { calls: 0, units: 0 };
    intervals[index].values.set(label, {
      calls: current.calls + 1,
      units: current.units + Number(event.units || 0),
    });
  }

  const series = topLabels.map((label, index) => ({
    key: label,
    label: totals.get(label)?.label || label,
    endpoint: totals.get(label)?.endpoint || null,
    technicalLabel: totals.get(label)?.technicalLabel || label,
    color: getUsageChartColor(index, topLabels.length),
    totalUnits: totals.get(label)?.units || 0,
    totalCalls: totals.get(label)?.calls || 0,
    values: intervals.map((interval) => interval.values.get(label)?.calls || 0),
    unitValues: intervals.map((interval) => interval.values.get(label)?.units || 0),
  }));
  const maxValue = Math.max(1, ...series.flatMap((item) => item.values));
  const axisIndexes = Array.from(new Set([0, Math.floor((intervals.length - 1) / 2), intervals.length - 1]));

  return {
    intervals: intervals.map(({ key, start, end, label, rangeLabel }) => ({ key, start, end, label, rangeLabel })),
    series,
    minTimestamp: alignedStart,
    maxTimestamp: alignedEnd || alignedStart + intervalMs,
    maxValue,
    axisLabels: axisIndexes.map((index) => ({
      key: `${intervals[index].key}-axis`,
      label: intervals[index].label,
    })),
    totalEvents: orderedEvents.length,
    timezoneMode,
  };
}

function UsageLineChart({ title, subtitle, data }) {
  const [selectedLabels, setSelectedLabels] = useState([]);
  const [hoveredIndex, setHoveredIndex] = useState(null);

  const visibleSeries = useMemo(
    () => (selectedLabels.length
      ? data.series.filter((series) => selectedLabels.includes(series.key))
      : data.series),
    [data.series, selectedLabels]
  );

  if (!data.series.length || !data.intervals.length) {
    return (
      <section className="usage-graph-card">
        <div className="card-head">
          <h4>{title}</h4>
          <p>{subtitle}</p>
        </div>
        <p className="muted">Not enough recent activity to plot yet.</p>
      </section>
    );
  }

  const width = 360;
  const height = 180;
  const paddingX = 18;
  const paddingTop = 14;
  const paddingBottom = 18;
  const chartWidth = width - paddingX * 2;
  const chartHeight = height - paddingTop - paddingBottom;
  const maxValue = Math.max(1, ...visibleSeries.flatMap((series) => series.values));
  const stepWidth = data.intervals.length > 1 ? chartWidth / (data.intervals.length - 1) : chartWidth;
  const safeHoveredIndex = hoveredIndex == null ? data.intervals.length - 1 : hoveredIndex;
  const hoverX = data.intervals.length > 1 ? paddingX + safeHoveredIndex * stepWidth : paddingX + chartWidth / 2;
  const tooltipLeft = Math.min(92, Math.max(8, (hoverX / width) * 100));
  const tooltipValues = visibleSeries
    .map((series) => ({
      label: series.label,
      endpoint: series.endpoint,
      technicalLabel: series.technicalLabel,
      color: series.color,
      calls: series.values[safeHoveredIndex] || 0,
      units: series.unitValues[safeHoveredIndex] || 0,
    }))
    .filter((item) => item.calls > 0)
    .sort((a, b) => b.calls - a.calls || b.units - a.units);

  function getPoint(index, value) {
    const x = data.intervals.length > 1 ? paddingX + index * stepWidth : paddingX + chartWidth / 2;
    const y = paddingTop + chartHeight - (value / maxValue) * chartHeight;
    return { x, y };
  }

  function buildSmoothPath(values) {
    const points = values.map((value, index) => ({ ...getPoint(index, value), value }));

    if (!points.length) return "";
    if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
    if (points.length === 2) return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;

    let path = `M ${points[0].x} ${points[0].y}`;
    for (let index = 0; index < points.length - 1; index += 1) {
      const previous = points[index - 1] || points[index];
      const current = points[index];
      const next = points[index + 1];
      const following = points[index + 2] || next;

      const control1X = current.x + (next.x - previous.x) / 6;
      const control1Y = current.y + (next.y - previous.y) / 6;
      const control2X = next.x - (following.x - current.x) / 6;
      const control2Y = next.y - (following.y - current.y) / 6;

      path += ` C ${control1X} ${control1Y}, ${control2X} ${control2Y}, ${next.x} ${next.y}`;
    }
    return path;
  }

  function toggleSeries(label) {
    setSelectedLabels((current) => (
      current.includes(label)
        ? current.filter((item) => item !== label)
        : [...current, label]
    ));
  }

  return (
    <section className="usage-graph-card">
      <div className="card-head">
        <h4>{title}</h4>
        <p>{subtitle}</p>
      </div>
      <div className="usage-line-legend">
        {data.series.map((series) => (
          <button
            className={`usage-line-legend-item ${!selectedLabels.length || selectedLabels.includes(series.key) ? "active" : "muted"}`}
            key={series.key}
            type="button"
            onClick={() => toggleSeries(series.key)}
          >
            <span className="usage-line-swatch" style={{ background: series.color }} />
            <strong title={series.technicalLabel}>{series.label}</strong>
            <span>{series.totalCalls} calls</span>
          </button>
        ))}
      </div>
      <div className="usage-line-shell" onMouseLeave={() => setHoveredIndex(null)}>
        {hoveredIndex != null ? (
          <div className="usage-line-tooltip" style={{ left: `${tooltipLeft}%` }}>
            <strong>{data.intervals[safeHoveredIndex]?.rangeLabel || data.intervals[safeHoveredIndex]?.label}</strong>
            {tooltipValues.length ? tooltipValues.map((item) => (
              <span key={`${title}-${item.technicalLabel}`}>
                <i style={{ background: item.color }} />
                {item.label}: {item.calls} calls | {item.units}u
              </span>
            )) : (
              <span>No calls in this interval</span>
            )}
            {tooltipValues.length ? tooltipValues.map((item) => (
              item.endpoint ? (
                <span className="usage-line-tooltip-endpoint" key={`${title}-${item.technicalLabel}-endpoint`}>
                  Endpoint: {item.endpoint}
                </span>
              ) : null
            )) : null}
          </div>
        ) : null}
        <svg
          className="usage-line-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${title} line chart`}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = paddingTop + chartHeight - chartHeight * ratio;
            return <line className="usage-line-grid" key={ratio} x1={paddingX} y1={y} x2={width - paddingX} y2={y} />;
          })}
          {hoveredIndex != null ? (
            <line
              className="usage-line-focus"
              x1={hoverX}
              y1={paddingTop}
              x2={hoverX}
              y2={paddingTop + chartHeight}
            />
          ) : null}
          {visibleSeries.map((series) => (
            <g key={series.key}>
              <path className="usage-line-path" fill="none" d={buildSmoothPath(series.values)} stroke={series.color} />
              {hoveredIndex != null && series.values[safeHoveredIndex] > 0 ? (() => {
                const { x, y } = getPoint(safeHoveredIndex, series.values[safeHoveredIndex]);
                return (
                  <circle
                    className="usage-line-dot is-active"
                    cx={x}
                    cy={y}
                    r="4.5"
                    fill={series.color}
                  />
                );
              })() : null}
            </g>
          ))}
          {data.intervals.map((interval, index) => {
            const hitWidth = data.intervals.length > 1 ? Math.max(18, stepWidth) : chartWidth;
            const x = (data.intervals.length > 1 ? paddingX + index * stepWidth : paddingX + chartWidth / 2) - hitWidth / 2;
            return (
              <rect
                key={`${interval.key}-hit`}
                className="usage-line-hitbox"
                x={x}
                y={paddingTop}
                width={hitWidth}
                height={chartHeight}
                fill="transparent"
                onMouseEnter={() => setHoveredIndex(index)}
              />
            );
          })}
        </svg>
        <div className="usage-line-axis">
          {data.axisLabels.map((item) => (
            <span key={item.key}>{item.label}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Settings() {
  const [auditFilter, setAuditFilter] = useState("all");
  const currentMonth = new Date().getMonth() + 1;
  const currentYear = new Date().getFullYear();
  const [pendingRevokeKey, setPendingRevokeKey] = useState(null);
  const [revokeConfirmationText, setRevokeConfirmationText] = useState("");
  const [usageSource, setUsageSource] = useState("api");
  const [usageTimezone, setUsageTimezone] = useState("IST");
  const [usageRecentWindow, setUsageRecentWindow] = useState("30d");
  const [usageMonth, setUsageMonth] = useState(currentMonth);
  const [usageYear, setUsageYear] = useState(currentYear);
  const [selectedUsageApiKeyId, setSelectedUsageApiKeyId] = useState("all");
  const [usageLoading, setUsageLoading] = useState(false);
  const [scopedUsageSummary, setScopedUsageSummary] = useState(null);
  const [scopedUsageEvents, setScopedUsageEvents] = useState([]);
  const {
    activeView, apiKeys, apiKeyName, setApiKeyName, newRawKey, setNewRawKey,
    createKey, revokeKey, busy, copyText, // Keys
    providerStatuses, providerInputs, setProviderInput, saveProviderKey, deleteProviderKey, // Providers
    quotaStatus, fetchUsageAnalytics, // Usage
    webhooks, webhookDeliveries, webhookUrl, setWebhookUrl, webhookSecret, setWebhookSecret,
    webhookEvents, toggleWebhookEvent, createWebhook, removeWebhook, // Webhooks
    workspaces, activeWorkspace, workspaceName, setWorkspaceName, workspaceMembers,
    memberEmail, setMemberEmail, memberRole, setMemberRole, createWorkspace, switchWorkspace, addWorkspaceMember, // Workspaces
    auditLogs // Audit
  } = useApp();
  const revokeTextMatches = useMemo(() => revokeConfirmationText.trim() === "REVOKE", [revokeConfirmationText]);
  const selectedUsageApiKey = useMemo(
    () => apiKeys.find((item) => String(item.id) === String(selectedUsageApiKeyId)) || null,
    [apiKeys, selectedUsageApiKeyId]
  );
  const recentUsageEvents = useMemo(
    () => filterUsageEventsByRecentWindow(
      [...(scopedUsageEvents || [])]
        .map((event) => ({ ...event, timestamp: parseUsageTimestamp(event.created_at) }))
        .filter((event) => Number.isFinite(event.timestamp))
        .sort((a, b) => a.timestamp - b.timestamp),
      usageRecentWindow
    ),
    [scopedUsageEvents, usageRecentWindow]
  );
  const endpointUsage = useMemo(
    () => buildUsageSeries(
      recentUsageEvents.filter((event) => {
        const feature = String(event.feature || "");
        return !feature.startsWith("request:") && feature !== "engine.security";
      }),
      (event) => event.feature,
      { timezoneMode: usageTimezone, recentWindow: usageRecentWindow }
    ),
    [recentUsageEvents, usageTimezone, usageRecentWindow]
  );
  const usageYearOptions = useMemo(
    () => Array.from({ length: 6 }, (_, index) => currentYear - index),
    [currentYear]
  );
  const selectedMonthLabel = useMemo(
    () => MONTH_OPTIONS.find((month) => month.value === usageMonth)?.label || "Selected month",
    [usageMonth]
  );
  const selectedRecentWindowLabel = useMemo(
    () => RECENT_WINDOW_OPTIONS.find((option) => option.value === usageRecentWindow)?.label || "All",
    [usageRecentWindow]
  );
  const selectedPeriodLimit = scopedUsageSummary?.limits?.monthly_units ?? quotaStatus?.limit_units ?? null;
  const selectedPeriodRemaining = selectedPeriodLimit != null
    ? Math.max(0, Number(selectedPeriodLimit) - Number(scopedUsageSummary?.usage?.unit_count || 0))
    : null;
  const entityUsageStats = useMemo(
    () => Object.entries(scopedUsageSummary?.entity_counts || {})
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
    [scopedUsageSummary]
  );
  const totalDetectedEntities = useMemo(
    () => entityUsageStats.reduce((sum, [, count]) => sum + Number(count || 0), 0),
    [entityUsageStats]
  );

  useEffect(() => {
    if (!pendingRevokeKey) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape" && !busy) {
        setPendingRevokeKey(null);
        setRevokeConfirmationText("");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pendingRevokeKey, busy]);

  useEffect(() => {
    if (activeView !== "usage") return undefined;

    let cancelled = false;
    const options = {
      source: usageSource,
      month: usageMonth,
      year: usageYear,
      ...(usageSource === "api" && selectedUsageApiKeyId !== "all" ? { api_key_id: selectedUsageApiKeyId } : {}),
    };

    setUsageLoading(true);
    fetchUsageAnalytics(options)
      .then(({ summary, events }) => {
        if (cancelled) return;
        setScopedUsageSummary(summary);
        setScopedUsageEvents(events || []);
      })
      .catch(() => {
        if (cancelled) return;
        setScopedUsageSummary(null);
        setScopedUsageEvents([]);
      })
      .finally(() => {
        if (!cancelled) setUsageLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeView, usageSource, usageMonth, usageYear, selectedUsageApiKeyId]);

  function requestRevoke(key) {
    setPendingRevokeKey(key);
    setRevokeConfirmationText("");
  }

  function cancelRevoke() {
    if (busy) return;
    setPendingRevokeKey(null);
    setRevokeConfirmationText("");
  }

  async function confirmRevoke() {
    if (!pendingRevokeKey || !revokeTextMatches || busy) return;
    await revokeKey(pendingRevokeKey.id);
    setPendingRevokeKey(null);
    setRevokeConfirmationText("");
  }

  // Determine title and description based on active setting view
  let title = "", desc = "", icon = null;
  if (activeView === "keys") { title = "API Keys"; desc = "Provision and manage API authentication tokens."; icon = <Icons.IconKey />; }
  if (activeView === "providers") { title = "LLM Providers"; desc = "Manage credentials for OpenAI, Groq, and Google."; icon = <Icons.IconProvider />; }
  if (activeView === "usage") { title = "Usage & Quotas"; desc = "Monitor requests, tokens, and billing capacity."; icon = <Icons.IconUsage />; }
  if (activeView === "webhooks") { title = "Webhooks"; desc = "Configure endpoint callbacks for system events."; icon = <Icons.IconWebhook />; }
  if (activeView === "workspaces") { title = "Workspaces"; desc = "Manage team resources and RBAC roles."; icon = <Icons.IconWorkspace />; }
  if (activeView === "audit") { title = "Audit Logs"; desc = "Real-time Flight Data Recorder. Inspect all application changes and agent swarm events."; icon = <Icons.IconUsage />; }

  return (
    <>
      <div className="feature-page">
      <FeaturePageHeader icon={icon} iconBg="var(--surface)" title={title} desc={desc} />

      {activeView === "keys" && (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Create Key</h3>
              <p>Generate a new API key for external clients, scripts, and direct API access.</p>
            </div>
            <form className="form-grid" onSubmit={createKey}>
              <Field label="Key Name"><input value={apiKeyName} onChange={(e) => setApiKeyName(e.target.value)} required /></Field>
              <button className="btn-primary" disabled={busy} type="submit">{busy ? "Creating..." : "Generate Key"}</button>
            </form>
            <hr style={{ border: "1px solid var(--border)", margin: "1.5rem 0" }} />
            
            <div className="card-head">
              <h3>Dashboard Access</h3>
              <p>Logged-in dashboard activity now uses your workspace session. API keys here are for external clients, scripts, and direct API integrations.</p>
            </div>
            <div className="sublist">
              <article className="sublist-item">
                <h4>Session Auth</h4>
                <p className="sublist-meta">PII, Playground, Console, Vault, Sandbox, Agents, and other in-app features run with your signed-in account session.</p>
              </article>
              <article className="sublist-item">
                <h4>External Access</h4>
                <p className="sublist-meta">Use generated API keys when calling the public API from outside this dashboard. Only the key prefix is visible after creation.</p>
              </article>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Active Keys</h3>
              <p>Keys configured in your workspace.</p>
            </div>
            <div className="sublist stagger-children">
              {apiKeys.map((k) => (
                <article className="sublist-item row" key={k.id}>
                  <div>
                    <h4>{k.name}</h4>
                    <p className="sublist-meta">{k.key_prefix}... • {new Date(k.created_at).toLocaleDateString()}</p>
                  </div>
                  <button className="btn-danger btn-sm" type="button" onClick={() => requestRevoke(k)}>Revoke</button>
                </article>
              ))}
              {!apiKeys.length && <p className="muted">No active keys.</p>}
            </div>
          </section>
        </div>
      )}

      {activeView === "providers" && (
        <div className="provider-grid stagger-children">
          {providerStatuses.map((p) => (
            <section className="card compact" key={p.provider}>
              <div className="card-head">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ textTransform: "capitalize" }}>{p.provider}</h3>
                  <ResultBadge type={p.is_configured ? "safe" : "neutral"}>{p.is_configured ? "Configured" : "Missing"}</ResultBadge>
                </div>
                {p.is_configured && <p className="muted" style={{ marginTop: "0.2rem" }}>Active Key: {p.prefix}...</p>}
              </div>
              <form className="form-grid" onSubmit={(e) => { e.preventDefault(); saveProviderKey(p.provider); }}>
                <Field label="API Key">
                  <input type="password" value={providerInputs[p.provider] || ""} onChange={(e) => setProviderInput(p.provider, e.target.value)} placeholder="sk-..." required />
                </Field>
                <div className="row">
                  <button className="btn-primary" disabled={busy} type="submit">Save</button>
                  {p.is_configured && <button className="btn-danger" disabled={busy} type="button" onClick={() => deleteProviderKey(p.provider)}>Delete</button>}
                </div>
              </form>
            </section>
          ))}
        </div>
      )}

      {activeView === "usage" && (
        <div className="usage-layout">
          <section className="card usage-summary-card">
            <div className="card-head">
              <h3>Monthly Aggregation</h3>
              <p>Usage totals for {selectedMonthLabel} {usageYear}.</p>
            </div>
            <div className="usage-filter-bar">
              <div className="auth-switch usage-source-switch">
                <button
                  className={usageSource === "workspace" ? "active" : ""}
                  type="button"
                  onClick={() => setUsageSource("workspace")}
                >
                  Workspace
                </button>
                <button
                  className={usageSource === "api" ? "active" : ""}
                  type="button"
                  onClick={() => setUsageSource("api")}
                >
                  API
                </button>
              </div>
              {usageSource === "api" ? (
                <select
                  className="usage-key-select"
                  value={selectedUsageApiKeyId}
                  onChange={(event) => setSelectedUsageApiKeyId(event.target.value)}
                >
                  <option value="all">All API Keys</option>
                  {apiKeys.map((key) => (
                    <option key={key.id} value={key.id}>{key.name}</option>
                  ))}
                </select>
              ) : null}
            </div>
            {scopedUsageSummary ? (
              <>
                <div className="stats-row">
                  <article className="stat-card"><span>Total Units</span><strong>{scopedUsageSummary.usage.unit_count}</strong></article>
                  <article className="stat-card"><span>Tokens Used</span><strong>{scopedUsageSummary.usage.token_count}</strong></article>
                  <article className="stat-card"><span>Requests Executed</span><strong>{scopedUsageSummary.usage.request_count}</strong></article>
                  <article className="stat-card"><span>Tracked Scope</span><strong>{usageSource === "workspace" ? "Workspace" : (selectedUsageApiKey?.name || "All API Keys")}</strong></article>
                  <article className="stat-card"><span>Monthly Limit</span><strong>{selectedPeriodLimit?.toLocaleString?.() ?? "N/A"}</strong></article>
                  <article className="stat-card"><span>Remaining Units</span><strong>{selectedPeriodRemaining?.toLocaleString?.() ?? "N/A"}</strong></article>
                </div>
                <div className="card-head usage-entity-head">
                  <h3>Detected Entity Stats</h3>
                  <p>Aggregate-only counts for the selected period and scope. No raw sensitive values are stored in usage analytics.</p>
                </div>
                {entityUsageStats.length ? (
                  <div className="stats-row usage-entity-stats">
                    <article className="stat-card">
                      <span>Total Entities</span>
                      <strong>{totalDetectedEntities}</strong>
                    </article>
                    {entityUsageStats.map(([kind, count]) => (
                      <article className="stat-card" key={kind}>
                        <span>{formatEntityLabel(kind)}</span>
                        <strong>{count}</strong>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="muted usage-entity-empty">No aggregate entity counts recorded for this selection yet.</p>
                )}
              </>
            ) : <p className="muted">{usageLoading ? "Loading usage statistics..." : "No usage statistics available."}</p>}
          </section>
          <section className="card usage-events-card">
            <div className="card-head usage-events-head">
              <div>
                <h3>Recent Traffic</h3>
                <p>{usageLoading ? "Loading..." : `${recentUsageEvents.length} events • ${selectedRecentWindowLabel} • ${usageTimezone}`}</p>
              </div>
              <div className="usage-head-controls">
                <div className="usage-period-filters usage-head-selects">
                  <select
                    className="usage-filter-select"
                    value={usageMonth}
                    onChange={(event) => setUsageMonth(Number(event.target.value))}
                  >
                    {MONTH_OPTIONS.map((month) => (
                      <option key={month.value} value={month.value}>{month.label}</option>
                    ))}
                  </select>
                  <select
                    className="usage-filter-select"
                    value={usageYear}
                    onChange={(event) => setUsageYear(Number(event.target.value))}
                  >
                    {usageYearOptions.map((year) => (
                      <option key={year} value={year}>{year}</option>
                    ))}
                  </select>
                  <select
                    className="usage-filter-select usage-recent-filter"
                    value={usageRecentWindow}
                    onChange={(event) => setUsageRecentWindow(event.target.value)}
                  >
                    {RECENT_WINDOW_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div className="auth-switch usage-timezone-switch">
                  {Object.keys(USAGE_TIMEZONES).map((zone) => (
                    <button
                      key={zone}
                      className={usageTimezone === zone ? "active" : ""}
                      type="button"
                      onClick={() => setUsageTimezone(zone)}
                    >
                      {zone}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {recentUsageEvents.length ? (
              <div className="usage-graph-panel">
                <UsageLineChart
                  title="By Endpoint"
                  subtitle="Calls per time interval for the busiest recent endpoints."
                  data={endpointUsage}
                />
              </div>
            ) : !usageLoading ? (
              <p className="muted">
                {usageSource === "api" ? "No API usage events recorded yet for this selection." : "No workspace usage events recorded yet."}
              </p>
            ) : null}
          </section>
        </div>
      )}
{activeView === "webhooks" && (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Add Webhook</h3>
              <p>Configure an endpoint to receive system events.</p>
            </div>
            <form className="form-grid" onSubmit={createWebhook}>
              <Field label="URL Protocol">
                <input type="url" value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} required placeholder="https://..." />
              </Field>
              <Field label="Signing Secret (Optional)">
                <input value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} />
              </Field>
              <div className="field">
                <span>Subscribed Events</span>
                <div className="chip-grid">
                  {["workflow.completed", "workflow.failed", "quota.warning", "security.threat"].map((ev) => (
                    <label className="chip" key={ev}>
                      <input type="checkbox" checked={webhookEvents.includes(ev)} onChange={() => toggleWebhookEvent(ev)} />
                      <span>{ev}</span>
                    </label>
                  ))}
                </div>
              </div>
              <button className="btn-primary" disabled={busy} type="submit">Create Hook</button>
            </form>
          </section>

          <section className="card">
            <div className="card-head"><h3>Active Endpoints</h3></div>
            <div className="sublist stagger-children">
              {webhooks.map((w) => (
                <article className="sublist-item row" key={w.id}>
                  <div>
                    <h4>{w.url}</h4>
                    <p className="sublist-meta">Events: {w.events.join(", ")}</p>
                  </div>
                  <button className="btn-danger btn-sm" onClick={() => removeWebhook(w.id)}>Remove</button>
                </article>
              ))}
              {!webhooks.length && <p className="muted">No webhooks attached.</p>}
            </div>
            
            <div className="card-head" style={{ marginTop: "1.5rem" }}><h3>Recent Deliveries</h3></div>
            <div className="sublist stagger-children">
              {webhookDeliveries.map((w) => (
                <article className="sublist-item row" key={w.id}>
                  <div>
                    <h4>{w.event}</h4>
                    <p className="sublist-meta">Code: {w.status_code} • {new Date(w.created_at).toLocaleString()}</p>
                  </div>
                  <ResultBadge type={w.status_code === 200 ? "safe" : "danger"}>HTTP {w.status_code}</ResultBadge>
                </article>
              ))}
              {!webhookDeliveries.length && <p className="muted">No delivery logs tracked yet.</p>}
            </div>
          </section>
        </div>
      )}

      {activeView === "workspaces" && (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Active Context</h3>
              <p>You are managing resources in <strong style={{ color: "var(--accent)" }}>{activeWorkspace?.name || "Unknown"}</strong>.</p>
            </div>
            <form className="form-grid" onSubmit={createWorkspace}>
              <Field label="New Workspace Name">
                <input value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} required />
              </Field>
              <button className="btn-primary" disabled={busy} type="submit">Create Hub</button>
            </form>
            
            <div className="card-head" style={{ marginTop: "1rem" }}>
              <h3>Available Workspaces</h3>
            </div>
            <div className="sublist stagger-children">
              {workspaces.map((w) => (
                <article className="sublist-item row" key={w.id}>
                  <div>
                    <h4>{w.name}</h4>
                    <p className="sublist-meta">ID: {w.id}</p>
                  </div>
                  {activeWorkspace?.id === w.id ? (
                    <ResultBadge type="safe">Active</ResultBadge>
                  ) : (
                    <button className="btn-ghost btn-sm" onClick={() => switchWorkspace(w.id)}>Switch Context</button>
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Invite Member</h3>
              <p>Add people to <strong style={{color: "var(--accent)"}}>{activeWorkspace?.name}</strong>.</p>
            </div>
            <form className="form-grid" onSubmit={addWorkspaceMember}>
              <Field label="Identity">
                <input type="email" value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} required placeholder="user@domain.com" />
              </Field>
              <Field label="RBAC Policy">
                <select value={memberRole} onChange={(e) => setMemberRole(e.target.value)}>
                  <option value="owner">Owner (Full Admin)</option>
                  <option value="admin">Admin (Keys & Billing)</option>
                  <option value="developer">Developer (Playground Access)</option>
                  <option value="viewer">Viewer (Read Logs)</option>
                </select>
              </Field>
              <button className="btn-primary" disabled={busy} type="submit">Grant Access</button>
            </form>
            
            <div className="card-head" style={{ marginTop: "1rem" }}>
              <h3>Current Access Matrix</h3>
            </div>
            <div className="sublist stagger-children">
              {workspaceMembers.map((m) => (
                <article className="sublist-item row" key={m.id}>
                  <div>
                    <h4>{m.email}</h4>
                    <p className="sublist-meta" style={{ textTransform: "uppercase" }}>{m.role}</p>
                  </div>
                </article>
              ))}
              {!workspaceMembers.length && <p className="muted">No explicit members in matrix. Owner overrides apply.</p>}
            </div>
          </section>
        </div>
      )}

      {activeView === "audit" && (
        <section className="card" style={{ maxWidth: "1200px" }}>
          <div className="card-head">
            <h3>Audit Trace</h3>
            <p>Live stream of structural system mutations and agent decisions. Events are immutable.</p>
          </div>
           <div className="sublist stagger-children">
            <div style={{ display: "flex", gap: "1rem", marginBottom: "1.5rem", borderBottom: "1px solid var(--border)", paddingBottom: "1rem" }}>
  <button 
    onClick={() => setAuditFilter("all")}
    style={{ background: "none", border: "none", cursor: "pointer", color: auditFilter === "all" ? "var(--indigo)" : "var(--ink-light)", fontWeight: auditFilter === "all" ? "bold" : "normal", borderBottom: auditFilter === "all" ? "2px solid var(--indigo)" : "none", padding: "0.5rem" }}
  >
    All Activity
  </button>
  <button 
    onClick={() => setAuditFilter("critical")}
    style={{ background: "none", border: "none", cursor: "pointer", color: auditFilter === "critical" ? "var(--red)" : "var(--ink-light)", fontWeight: auditFilter === "critical" ? "bold" : "normal", borderBottom: auditFilter === "critical" ? "2px solid var(--red)" : "none", padding: "0.5rem" }}
  >
    Critical Breaches
  </button>
</div>

                    {auditLogs?.filter(log => !log.action.toLowerCase().includes("auth"))
            .filter(log => auditFilter === "all" || log.action.includes("BLOCKED"))
            .map((log) => (


              <article className="sublist-item" key={log.id} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <span style={{ 
                        fontSize: "0.7rem", 
                        padding: "0.2rem 0.6rem", 
                        borderRadius: "10px", 
                        background: log.action.includes("BLOCKED") ? "var(--red-light)" : "var(--grey-100)", 
                        color: log.action.includes("BLOCKED") ? "var(--red)" : "var(--grey-900)",
                        fontWeight: "bold",
                        border: "1px solid"
                      }}>
                        {log.action.includes("BLOCKED") ? "CRITICAL" : "EVENT"}
                      </span>
                      <h4 style={{ margin: 0, textTransform: "uppercase", fontSize: "0.85rem", color: "var(--indigo)" }}>
                        {log.action.replace(/_/g, " ")}
                      </h4>
                    </div>


                    <span className="muted" style={{ fontSize: "0.75rem" }}>{log.target_type || "System"}</span>
                  </div>
                  <span className="muted" style={{ fontSize: "0.75rem" }}>
                    {new Date(log.created_at).toLocaleString()}
                  </span>
                </div>
                
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", fontSize: "0.8rem", padding: "0.75rem", background: "var(--surface)", borderRadius: "var(--radius)" }}>
                    <div>
                        <strong className="muted" style={{ display: "block", marginBottom: "0.2rem" }}>Request ID</strong>
                        <span style={{ fontFamily: "monospace", color: "var(--ink)" }}>{log.request_id || "System Trigger"}</span>
                    </div>
                    <div>
                        <strong className="muted" style={{ display: "block", marginBottom: "0.2rem" }}>IP Address</strong>
                        <span style={{ fontFamily: "monospace", color: "var(--ink)" }}>{log.ip_address || "Internal Core"}</span>
                    </div>
                </div>

                {Object.keys(log.metadata || {}).length > 0 && (
                  <div style={{ padding: "0.75rem", background: "var(--grey-100)", border: "1px solid var(--border)", color: "var(--grey-900)", borderRadius: "var(--radius)", overflowX: "auto" }}>

                     <pre style={{ margin: 0, fontSize: "0.8rem", fontFamily: "var(--font-mono)", lineHeight: 1.6 }}>{JSON.stringify(log.metadata, null, 2)}</pre>
                  </div>
                )}
              </article>
            ))}
            {(!auditLogs || auditLogs.length === 0) && (
              <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>No audit events found for this workspace.</p>
            )}
          </div>
        </section>
      )}

    </div>

      {newRawKey && (
        <div className="popup-overlay">
          <div className="popup-box">
            <h2>Save Your New API Key</h2>
            <p>This key will only be shown once. Please store it somewhere safe immediately. Use it for external API access, scripts, or integrations.</p>
            <div className="key-display">{newRawKey}</div>
            <div style={{ display: "flex", gap: "1rem" }}>
              <button className="btn-ghost btn-full" onClick={() => copyText(newRawKey)}>Copy to Clipboard</button>
              <button className="btn-primary btn-full" onClick={() => setNewRawKey("")}>I Have Saved It</button>
            </div>
          </div>
        </div>
      )}

      {pendingRevokeKey ? (
        <div className="popup-overlay" onClick={cancelRevoke} role="presentation">
          <div
            className="popup-box confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="revoke-confirm-title"
            aria-describedby="revoke-confirm-description"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-dialog-icon" aria-hidden="true">
              <Icons.IconKey />
            </div>
            <h2 id="revoke-confirm-title">Revoke this API key?</h2>
            <p id="revoke-confirm-description">
              This will immediately disable <strong>{pendingRevokeKey.name}</strong> for this workspace. Type <strong>REVOKE</strong> below to confirm.
            </p>
            <div className="field revoke-confirm-field">
              <span>Confirmation Text</span>
              <input
                autoFocus
                value={revokeConfirmationText}
                onChange={(event) => setRevokeConfirmationText(event.target.value)}
                placeholder="Type REVOKE"
              />
              <small className="muted revoke-confirm-hint">Exact match required.</small>
            </div>
            <div className="confirm-actions">
              <button className="btn-ghost btn-full" type="button" onClick={cancelRevoke} disabled={busy}>
                Cancel
              </button>
              <button className="btn-danger btn-full" type="button" onClick={confirmRevoke} disabled={!revokeTextMatches || busy}>
                {busy ? "Revoking..." : "Revoke Key"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}


