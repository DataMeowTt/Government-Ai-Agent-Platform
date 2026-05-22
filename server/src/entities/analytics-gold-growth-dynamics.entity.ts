import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'analytics_gold_growth_dynamics' })
export class AnalyticsGoldGrowthDynamics {
  @PrimaryColumn({ type: 'varchar', length: 3 })
  country_code: string;

  @PrimaryColumn({ type: 'int' })
  year: number;

  @Column({ type: 'float', nullable: true, name: 'rGDP_growth_YoY_actual' })
  rGDP_growth_YoY_actual: number | null;

  @Column({ type: 'float', nullable: true, name: 'rGDP_growth_YoY_trend' })
  rGDP_growth_YoY_trend: number | null;

  @Column({ type: 'float', nullable: true, name: 'rGDP_growth_YoY_residual' })
  rGDP_growth_YoY_residual: number | null;

  @Column({ type: 'float', nullable: true, name: 'rGDP_growth_YoY_anomaly_score' })
  rGDP_growth_YoY_anomaly_score: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_YoY_actual' })
  GDP_growth_YoY_actual: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_YoY_trend' })
  GDP_growth_YoY_trend: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_YoY_residual' })
  GDP_growth_YoY_residual: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_YoY_anomaly_score' })
  GDP_growth_YoY_anomaly_score: number | null;

  @Column({ type: 'float', nullable: true, name: 'trend_deviation_actual' })
  trend_deviation_actual: number | null;

  @Column({ type: 'float', nullable: true, name: 'trend_deviation_trend' })
  trend_deviation_trend: number | null;

  @Column({ type: 'float', nullable: true, name: 'trend_deviation_residual' })
  trend_deviation_residual: number | null;

  @Column({ type: 'float', nullable: true, name: 'trend_deviation_anomaly_score' })
  trend_deviation_anomaly_score: number | null;
}