import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from "chart.js";

/** Large centered % labels on doughnut / pie slices (attach per-chart, not globally). */
export const doughnutPercentLabelsPlugin = {
  id: "doughnutPercentLabels",
  afterDatasetsDraw(chart: ChartJS) {
    const chartType = (chart.config as { type?: string }).type;
    if (chartType !== "doughnut" && chartType !== "pie") return;

    const dataset = chart.data.datasets[0];
    if (!dataset?.data?.length) return;
    const meta = chart.getDatasetMeta(0);
    const raw = dataset.data as number[];
    const total = raw.reduce((sum, v) => sum + (typeof v === "number" ? v : 0), 0);
    if (total <= 0) return;

    const { ctx } = chart;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    meta.data.forEach((arc, index) => {
      const value = typeof raw[index] === "number" ? raw[index] : 0;
      if (value <= 0) return;
      const pct = (value / total) * 100;
      const pos = arc.tooltipPosition(true);
      const x = pos?.x ?? arc.x;
      const y = pos?.y ?? arc.y;
      const fontSize = Math.max(15, Math.min(22, chart.width / 14));
      ctx.font = `700 ${fontSize}px Inter, system-ui, sans-serif`;
      ctx.fillStyle = "#ffffff";
      ctx.shadowColor = "rgba(15, 23, 42, 0.45)";
      ctx.shadowBlur = 4;
      ctx.fillText(`${pct.toFixed(1)}%`, x, y);
    });
    ctx.restore();
  },
};

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
);

export const DOUGHNUT_PERCENT_OPTIONS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: "bottom" as const,
      labels: { font: { size: 13, weight: 500 as const }, padding: 16 },
    },
    tooltip: {
      callbacks: {
        label: (ctx: { label?: string; parsed?: number; dataset: { data: number[] } }) => {
          const value = typeof ctx.parsed === "number" ? ctx.parsed : 0;
          const total = (ctx.dataset.data as number[]).reduce((a, b) => a + b, 0);
          const pct = total > 0 ? (value / total) * 100 : 0;
          return `${ctx.label ?? ""}: ${pct.toFixed(1)}%`;
        },
      },
    },
  },
};

export { Bar, Doughnut, Line } from "react-chartjs-2";

export const CHART_GRID = "rgba(148,163,184,0.35)";
export const BAKER_TEAL = "#14b8a6";
export const BAKER_ROSE = "#f43f5e";
export const BAKER_SLATE = "#64748b";

export function formatMoney(prefix: string, value: number) {
  return `${prefix}${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
