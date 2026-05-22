import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'analytics_gold_crisis_risk' })
export class AnalyticsGoldCrisisRisk {
  @PrimaryColumn() country_code: string;
  @PrimaryColumn() year: number;

  @Column({ type: 'float', nullable: true, name: 'REER_deviation_actual' }) REER_deviation_actual: number;
  @Column({ type: 'float', nullable: true, name: 'REER_deviation_anomaly_score' }) REER_deviation_anomaly_score: number;

  @Column({ type: 'float', nullable: true, name: 'spending_efficiency_actual' }) spending_efficiency_actual: number;
  @Column({ type: 'float', nullable: true, name: 'spending_efficiency_anomaly_score' }) spending_efficiency_anomaly_score: number;
}