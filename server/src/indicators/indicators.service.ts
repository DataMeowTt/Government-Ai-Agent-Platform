import { Injectable, OnModuleInit, Logger } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';

export interface Indicator {
  code: string;
  name: string;
  category: string;
  unit: string;
  table: string;
}

@Injectable()
export class IndicatorsService implements OnModuleInit {
  private readonly logger = new Logger(IndicatorsService.name);
  private indicators: Indicator[] = [];

  private readonly goldTables = [
    'gold_growth_dynamics',
    'gold_fiscal_monetary',
    'gold_crisis_risk',
    'gold_social_welfare',
    'gold_structural_composition',
  ];

  private readonly excludedColumns = new Set([
    'country_code', 'country', 'year',
    'income_group', 'development_group', 'completeness_score',
  ]);

  private readonly columnMetadata: Record<string, { category: string; unit: string; name?: string }> = {
    // Growth
    'rGDP_growth_YoY': { category: 'Growth', unit: '%', name: 'Real GDP Growth (YoY)' },
    'rolling_mean_5yr': { category: 'Growth', unit: '%', name: '5-Year Rolling Mean Growth' },
    'GDP_growth_YoY': { category: 'Growth', unit: '%', name: 'Nominal GDP Growth (YoY)' },
    'GDP_growth_trend_5yr': { category: 'Growth', unit: '%', name: 'GDP Growth Trend (5-year)' },
    'trend_deviation': { category: 'Growth', unit: '%', name: 'Trend Deviation' },
    'GDP_pc_growth_gap': { category: 'Growth', unit: '%', name: 'GDP per Capita Growth Gap' },
    'log_rGDP_pc_USD': { category: 'Growth', unit: 'log', name: 'Log Real GDP per Capita' },
    // Fiscal & Monetary
    'govdebt_GDP': { category: 'Fiscal', unit: '%', name: 'Government Debt (% GDP)' },
    'debt_change_YoY': { category: 'Fiscal', unit: '%', name: 'Debt Change (YoY)' },
    'govrev_GDP': { category: 'Fiscal', unit: '%', name: 'Government Revenue (% GDP)' },
    'govexp_GDP': { category: 'Fiscal', unit: '%', name: 'Government Expenditure (% GDP)' },
    'fiscal_balance_GDP': { category: 'Fiscal', unit: '%', name: 'Fiscal Balance (% GDP)' },
    'cumulative_deficit_5yr': { category: 'Fiscal', unit: '%', name: 'Cumulative Deficit (5-year)' },
    'ltrate': { category: 'Monetary', unit: '%', name: 'Long-term Interest Rate' },
    'infl': { category: 'Monetary', unit: '%', name: 'Inflation Rate' },
    'real_interest_rate': { category: 'Monetary', unit: '%', name: 'Real Interest Rate' },
    'tax_revenue_pct_GDP': { category: 'Fiscal', unit: '%', name: 'Tax Revenue (% GDP)' },
    'inflation_cpi': { category: 'Monetary', unit: '%', name: 'Inflation (CPI)' },
    'inflation_deflator': { category: 'Monetary', unit: '%', name: 'Inflation (GDP Deflator)' },
    'inflation_gap': { category: 'Monetary', unit: '%', name: 'Inflation Gap (CPI - Deflator)' },
    'rolling_3yr_avg_cpi': { category: 'Monetary', unit: '%', name: '3-Year Avg CPI Inflation' },
    // Crisis Risk
    'SovDebtCrisis': { category: 'Risk', unit: 'flag', name: 'Sovereign Debt Crisis' },
    'CurrencyCrisis': { category: 'Risk', unit: 'flag', name: 'Currency Crisis' },
    'BankingCrisis': { category: 'Risk', unit: 'flag', name: 'Banking Crisis' },
    'crisis_composite': { category: 'Risk', unit: '0-3', name: 'Crisis Composite Index' },
    'crisis_any': { category: 'Risk', unit: 'flag', name: 'Any Crisis' },
    'REER_deviation': { category: 'Risk', unit: '%', name: 'REER Deviation (%)' },
    'spending_efficiency': { category: 'Risk', unit: 'ratio', name: 'Spending Efficiency' },
    // Social Welfare
    'unemployment_total': { category: 'Social', unit: '%', name: 'Unemployment Rate (Total)' },
    'unemployment_youth': { category: 'Social', unit: '%', name: 'Youth Unemployment Rate' },
    'youth_unemployment_gap': { category: 'Social', unit: '%', name: 'Youth Unemployment Gap' },
    'youth_gap_ratio': { category: 'Social', unit: 'ratio', name: 'Youth Gap Ratio' },
    'self_employed_pct': { category: 'Social', unit: '%', name: 'Self-Employed (% of employment)' },
    'poverty_headcount': { category: 'Social', unit: '%', name: 'Poverty Headcount Ratio' },
    'poverty_change_5yr': { category: 'Social', unit: '%', name: 'Poverty Change (5-year)' },
    'urban_pop_pct': { category: 'Demographics', unit: '%', name: 'Urban Population (%)' },
    'urban_pop_growth': { category: 'Demographics', unit: '%', name: 'Urban Population Growth' },
    'pop_density': { category: 'Demographics', unit: 'people/km²', name: 'Population Density' },
    'log_pop_density': { category: 'Demographics', unit: 'log', name: 'Log Population Density' },
    'pop_growth': { category: 'Demographics', unit: '%', name: 'Population Growth (annual)' },
    'hcons_share': { category: 'Social', unit: '%', name: 'Household Consumption Share' },
    'hcons_growth': { category: 'Social', unit: '%', name: 'Household Consumption Growth' },
    'trade_pct_gdp': { category: 'Trade', unit: '%', name: 'Trade (% GDP)' },
    // Structural Composition
    'decade': { category: 'Structure', unit: 'year', name: 'Decade' },
    'GDP_value': { category: 'Structure', unit: 'current US$', name: 'GDP (current US$)' },
    'GFCF_value': { category: 'Investment', unit: 'current US$', name: 'Gross Fixed Capital Formation (USD)' },
    'GNI_value': { category: 'Structure', unit: 'current US$', name: 'GNI (current US$)' },
    'Agri_VA': { category: 'Structure', unit: 'current US$', name: 'Agriculture Value Added (USD)' },
    'Manuf_VA': { category: 'Structure', unit: 'current US$', name: 'Manufacturing Value Added (USD)' },
    'VA_FoodBev': { category: 'Structure', unit: 'current US$', name: 'Food & Beverage Value Added (USD)' },
    'GFCF_to_GDP': { category: 'Investment', unit: '%', name: 'GFCF (% GDP)' },
    'GNI_to_GDP': { category: 'Structure', unit: 'ratio', name: 'GNI to GDP Ratio' },
    'agri_va_share': { category: 'Structure', unit: '%', name: 'Agriculture Value Added (% GDP)' },
    'manuf_va_share': { category: 'Structure', unit: '%', name: 'Manufacturing Value Added (% GDP)' },
    'food_bev_share_manuf': { category: 'Structure', unit: '%', name: 'Food & Beverage Share of Manufacturing' },
    'flag_score': { category: 'Quality', unit: '0-3', name: 'Data Quality Flag' },
  };

  constructor(@InjectDataSource() private dataSource: DataSource) { }

  async onModuleInit() {
    await this.loadIndicators();
  }

  private async loadIndicators() {
    this.indicators = [];
    const seenCodes = new Set<string>();

    for (const table of this.goldTables) {
      const columns = await this.dataSource.query(
        `SELECT column_name
      FROM information_schema.columns
      WHERE table_name = $1
      ORDER BY ordinal_position`,
        [table]
      );

      for (const { column_name } of columns) {
        if (this.excludedColumns.has(column_name)) continue;

        if (seenCodes.has(column_name)) {
          this.logger.debug(`Skipping duplicate indicator: ${column_name} in ${table}`);
          continue;
        }

        const meta = this.columnMetadata[column_name] || {
          category: 'Other',
          unit: 'unknown',
          name: column_name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
        };

        this.indicators.push({
          code: column_name,
          name: meta.name || column_name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
          category: meta.category,
          unit: meta.unit,
          table: table,
        });

        seenCodes.add(column_name);
      }
    }

    this.logger.log(`Loaded ${this.indicators.length} unique indicators from ${this.goldTables.length} tables`);
  }

  findAll(): Indicator[] {
    return this.indicators;
  }

  findByCategory(category: string): Indicator[] {
    return this.indicators.filter(i => i.category.toLowerCase() === category.toLowerCase());
  }

  findByCode(code: string): Indicator | undefined {
    return this.indicators.find(i => i.code === code);
  }
}