import {
  ChartToTSEvent,
  ColumnType,
  getChartContext,
} from '@thoughtspot/ts-chart-sdk';
import _ from 'lodash';
import numeral from 'numeral';

let userNumberFormat = '0,0';

const formatValue = (value, format = '') => {
  if (format === '' || format == null) return numeral(value).format('0,0');
  return numeral(value).format(format);
};

const formatPercent = (value) => {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${numeral(value).format('0.0')}%`;
};

function getDataForColumn(column, dataArr) {
  const idx = _.findIndex(dataArr.columns, (colId) => column.id === colId);
  return _.map(dataArr.dataValue, (row) => row[idx]);
}

function getColumnValue(col, dataArr) {
  if (!col || !dataArr || !dataArr.columns) return 0;
  const vals = getDataForColumn(col, dataArr);
  return _.sum(vals);
}

function calculateKpiValues(chartModel) {
  const dataArr = chartModel.data?.[0]?.data ?? [];
  const configDimensions =
    chartModel.config?.chartConfig?.[1]?.dimensions ??
    chartModel.config?.chartConfig?.[0]?.dimensions ?? [];

  const mainDim = configDimensions.find((d) => d.key === 'x');
  const goalDim = configDimensions.find((d) => d.key === 'goal');
  const compDim = configDimensions.find((d) => d.key === 'y');

  const mainKpiCol = mainDim?.columns?.[0] ?? null;
  const goalCol = goalDim?.columns?.[0] ?? null;

  const mainKpiValue = mainKpiCol ? getColumnValue(mainKpiCol, dataArr) : 0;
  const goalValue = goalCol ? getColumnValue(goalCol, dataArr) : 0;

  const metricName = mainKpiCol?.name ?? '';

  const comparisonMeasures = (compDim?.columns ?? []).map((col) => {
    const value = getColumnValue(col, dataArr);
    const change =
      value !== 0 ? ((mainKpiValue - value) / Math.abs(value)) * 100 : 0;
    return { label: col.name, value, change };
  });

  return { mainKpiValue, goalValue, metricName, comparisonMeasures };
}

function updateChart(chartModel) {
  const { mainKpiValue, goalValue, metricName, comparisonMeasures } =
    calculateKpiValues(chartModel);

  const format = chartModel.visualProps?.numberFormat || userNumberFormat;
  const goalLabel = chartModel.visualProps?.goalLabel || 'GOAL';
  const threshold = parseFloat(chartModel.visualProps?.progressThreshold ?? 80);

  // Metric name / title
  const labelEl = document.getElementById('kpiLabel');
  if (labelEl) labelEl.textContent = metricName.toUpperCase();

  // Main KPI value
  document.getElementById('mainKpiValue').textContent = formatValue(
    mainKpiValue,
    format,
  );

  // Progress %
  const progressPct =
    goalValue > 0 ? Math.min((mainKpiValue / goalValue) * 100, 100) : 0;
  const isOnTrack = progressPct >= threshold;

  const progressIndicator = document.getElementById('progressIndicator');
  progressIndicator.textContent = `${isOnTrack ? '↑' : '↓'} ${numeral(progressPct).format('0')}% of goal`;
  progressIndicator.className = isOnTrack ? 'kpi-positive' : 'kpi-negative';

  // Progress bar fill
  document.getElementById('progressBarFill').style.width = `${progressPct}%`;

  // Goal label
  const goalValueEl = document.getElementById('goalValue');
  goalValueEl.textContent = `${goalLabel.toUpperCase()}: ${formatValue(goalValue, format)}`;

  // Comparison measures
  const measuresContainer = document.getElementById('kpiMeasures');
  measuresContainer.innerHTML = '';

  comparisonMeasures.forEach((m) => {
    const isPositive = m.change >= 0;
    const measureDiv = document.createElement('div');
    measureDiv.className = 'kpi-comparison-item';
    measureDiv.innerHTML = `
      <span class="comparison-label">${m.label.toUpperCase()}</span>
      <span class="${isPositive ? 'kpi-positive' : 'kpi-negative'}">${formatPercent(m.change)}</span>
    `;
    measuresContainer.appendChild(measureDiv);
  });
}

function insertCustomFont(customFontFaces) {
  customFontFaces.forEach((it) => {
    const font = new FontFace(it.family, `url(${it.url})`);
    document.fonts.add(font);
  });
}

async function render(ctx) {
  const chartModel = await ctx.getChartModel();
  const appConfig = ctx.getAppConfig();

  if (appConfig?.styleConfig?.customFontFaces?.length) {
    insertCustomFont(appConfig.styleConfig.customFontFaces);
  }

  updateChart(chartModel);
}

const renderChart = async (ctx) => {
  try {
    ctx.emitEvent(ChartToTSEvent.RenderStart);
    await render(ctx);
  } catch (e) {
    ctx.emitEvent(ChartToTSEvent.RenderError, { hasError: true, error: e });
  } finally {
    ctx.emitEvent(ChartToTSEvent.RenderComplete);
  }
};

(async () => {
  const ctx = await getChartContext({
    getDefaultChartConfig: (chartModel) => {
      const measureColumns = _.filter(
        chartModel.columns,
        (col) => col.type === ColumnType.MEASURE,
      );
      return [
        {
          key: 'column',
          dimensions: [
            { key: 'x', columns: measureColumns.length > 0 ? [measureColumns[0]] : [] },
            { key: 'goal', columns: measureColumns.length > 1 ? [measureColumns[1]] : [] },
            { key: 'y', columns: measureColumns.length > 2 ? measureColumns.slice(2) : [] },
          ],
        },
      ];
    },
    getQueriesFromChartConfig: (chartConfig) => {
      return chartConfig.map((config) =>
        _.reduce(
          config.dimensions,
          (acc, dimension) => ({
            queryColumns: [...acc.queryColumns, ...dimension.columns],
          }),
          { queryColumns: [] },
        ),
      );
    },
    renderChart,
    chartConfigEditorDefinition: [
      {
        key: 'column',
        label: 'KPI Goal Chart',
        descriptionText:
          'Requires at least 2 measures: the current value and the goal value. ' +
          'Add additional measures for comparisons (e.g. MOM, Last Year).',
        columnSections: [
          {
            key: 'x',
            label: 'Main KPI (current value)',
            allowAttributeColumns: false,
            allowMeasureColumns: true,
            allowTimeSeriesColumns: true,
            maxColumnCount: 1,
          },
          {
            key: 'goal',
            label: 'Goal value',
            allowAttributeColumns: false,
            allowMeasureColumns: true,
            allowTimeSeriesColumns: false,
            maxColumnCount: 1,
          },
          {
            key: 'y',
            label: 'Comparison measures (e.g. MOM, Last Year)',
            allowAttributeColumns: false,
            allowMeasureColumns: true,
            allowTimeSeriesColumns: false,
          },
        ],
      },
    ],
    visualPropEditorDefinition: {
      elements: [
        {
          key: 'numberFormat',
          type: 'text',
          defaultValue: '0,0',
          label: 'Number Format',
        },
        {
          key: 'goalLabel',
          type: 'text',
          defaultValue: 'GOAL',
          label: 'Goal Label',
        },
        {
          key: 'progressThreshold',
          type: 'text',
          defaultValue: '80',
          label: 'On-track threshold (%)',
        },
      ],
    },
    onPropChange: (_propKey, _propValue) => {
      renderChart(ctx);
    },
  });

  renderChart(ctx);
})();
