import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'gold_fiscal_monetary' })
export class GoldFiscalMonetary {
  @PrimaryColumn({ type: 'varchar', length: 3 })
  country_code: string;

  @PrimaryColumn({ type: 'int' })
  year: number;

  @Column({ type: 'text' })
  country: string;

  @Column({ type: 'float', nullable: true, name: 'govdebt_GDP' })
  govdebt_GDP: number | null;

  @Column({ type: 'float', nullable: true, name: 'debt_change_YoY' })
  debt_change_YoY: number | null;

  @Column({ type: 'float', nullable: true, name: 'govrev_GDP' })
  govrev_GDP: number | null;

  @Column({ type: 'float', nullable: true, name: 'govexp_GDP' })
  govexp_GDP: number | null;

  @Column({ type: 'float', nullable: true, name: 'fiscal_balance_GDP' })
  fiscal_balance_GDP: number | null;

  @Column({ type: 'float', nullable: true })
  cumulative_deficit_5yr: number | null;

  @Column({ type: 'float', nullable: true })
  ltrate: number | null;

  @Column({ type: 'float', nullable: true })
  infl: number | null;

  @Column({ type: 'float', nullable: true })
  real_interest_rate: number | null;

  @Column({ type: 'float', nullable: true, name: 'tax_revenue_pct_GDP' })
  tax_revenue_pct_GDP: number | null;

  @Column({ type: 'float', nullable: true })
  inflation_cpi: number | null;

  @Column({ type: 'float', nullable: true })
  inflation_deflator: number | null;

  @Column({ type: 'float', nullable: true })
  inflation_gap: number | null;

  @Column({ type: 'float', nullable: true })
  rolling_3yr_avg_cpi: number | null;

  @Column({ type: 'text', nullable: true })
  income_group: string | null;

  @Column({ type: 'text', nullable: true })
  development_group: string | null;

  @Column({ type: 'float' })
  completeness_score: number;
}