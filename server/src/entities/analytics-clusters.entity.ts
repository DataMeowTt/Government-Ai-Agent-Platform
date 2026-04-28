import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'analytics_clusters' })
export class AnalyticsClusters {
  @PrimaryColumn() country_code: string;
  @PrimaryColumn() year: number;
  @Column() cluster_id: number;
  @Column() method: string;
}