import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'analytics_gold_social_welfare' })
export class AnalyticsGoldSocialWelfare {
  @PrimaryColumn() country_code: string;
  @PrimaryColumn() year: number;

  @Column({ type: 'float', nullable: true, name: 'poverty_headcount_actual' }) poverty_headcount_actual: number;
  @Column({ type: 'float', nullable: true, name: 'poverty_headcount_anomaly_score' }) poverty_headcount_anomaly_score: number;

  @Column({ type: 'float', nullable: true, name: 'unemployment_total_actual' }) unemployment_total_actual: number;
  @Column({ type: 'float', nullable: true, name: 'unemployment_total_trend' }) unemployment_total_trend: number;
  @Column({ type: 'float', nullable: true, name: 'unemployment_total_anomaly_score' }) unemployment_total_anomaly_score: number;
}