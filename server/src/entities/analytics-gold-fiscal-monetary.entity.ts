import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'analytics_gold_fiscal_monetary' })
export class AnalyticsGoldFiscalMonetary {
  @PrimaryColumn() country_code: string;
  @PrimaryColumn() year: number;

  @Column({ type: 'float', nullable: true, name: 'govdebt_GDP_actual' }) govdebt_GDP_actual: number;
  @Column({ type: 'float', nullable: true, name: 'govdebt_GDP_trend' }) govdebt_GDP_trend: number;
  @Column({ type: 'float', nullable: true, name: 'govdebt_GDP_anomaly_score' }) govdebt_GDP_anomaly_score: number;

  @Column({ type: 'float', nullable: true, name: 'fiscal_balance_GDP_actual' }) fiscal_balance_GDP_actual: number;
  @Column({ type: 'float', nullable: true, name: 'fiscal_balance_GDP_trend' }) fiscal_balance_GDP_trend: number;
  @Column({ type: 'float', nullable: true, name: 'fiscal_balance_GDP_anomaly_score' }) fiscal_balance_GDP_anomaly_score: number;

  @Column({ type: 'float', nullable: true, name: 'inflation_cpi_actual' }) inflation_cpi_actual: number;
  @Column({ type: 'float', nullable: true, name: 'inflation_cpi_trend' }) inflation_cpi_trend: number;
  @Column({ type: 'float', nullable: true, name: 'inflation_cpi_anomaly_score' }) inflation_cpi_anomaly_score: number;
}