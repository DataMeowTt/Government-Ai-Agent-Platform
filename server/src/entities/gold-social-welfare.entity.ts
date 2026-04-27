import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'gold_social_welfare' })
export class GoldSocialWelfare {
  @PrimaryColumn({ type: 'varchar', length: 3 })
  country_code: string;

  @PrimaryColumn({ type: 'int' })
  year: number;

  @Column({ type: 'text' })
  country: string;

  @Column({ type: 'float', nullable: true })
  unemployment_total: number | null;

  @Column({ type: 'float', nullable: true })
  unemployment_youth: number | null;

  @Column({ type: 'float', nullable: true })
  youth_unemployment_gap: number | null;

  @Column({ type: 'float', nullable: true })
  youth_gap_ratio: number | null;

  @Column({ type: 'float', nullable: true })
  self_employed_pct: number | null;

  @Column({ type: 'float', nullable: true })
  poverty_headcount: number | null;

  @Column({ type: 'float', nullable: true })
  poverty_change_5yr: number | null;

  @Column({ type: 'float', nullable: true })
  urban_pop_pct: number | null;

  @Column({ type: 'float', nullable: true })
  urban_pop_growth: number | null;

  @Column({ type: 'float', nullable: true })
  pop_density: number | null;

  @Column({ type: 'float', nullable: true })
  log_pop_density: number | null;

  @Column({ type: 'float', nullable: true })
  pop_growth: number | null;

  @Column({ type: 'float', nullable: true })
  hcons_share: number | null;

  @Column({ type: 'float', nullable: true })
  hcons_growth: number | null;

  @Column({ type: 'float', nullable: true })
  trade_pct_gdp: number | null;

  @Column({ type: 'text', nullable: true })
  income_group: string | null;

  @Column({ type: 'text', nullable: true })
  development_group: string | null;

  @Column({ type: 'float' })
  completeness_score: number;
}