import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'gold_growth_dynamics' })
export class GoldGrowthDynamics {
  @PrimaryColumn({ type: 'varchar', length: 3 })
  country_code: string;

  @PrimaryColumn({ type: 'int' })
  year: number;

  @Column({ type: 'text' })
  country: string;

  @Column({ type: 'float', nullable: true, name: 'rGDP_growth_YoY' })
  rGDP_growth_YoY: number | null;

  @Column({ type: 'float', nullable: true })
  rolling_mean_5yr: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_YoY' })
  GDP_growth_YoY: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_trend_5yr' })
  GDP_growth_trend_5yr: number | null;

  @Column({ type: 'float', nullable: true })
  trend_deviation: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_pc_growth_gap' })
  GDP_pc_growth_gap: number | null;

  @Column({ type: 'float', nullable: true, name: 'log_rGDP_pc_USD' })
  log_rGDP_pc_USD: number | null;

  @Column({ type: 'text', nullable: true })
  income_group: string | null;

  @Column({ type: 'text', nullable: true })
  development_group: string | null;

  @Column({ type: 'float' })
  completeness_score: number;
}