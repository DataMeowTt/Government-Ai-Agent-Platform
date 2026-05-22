import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'analytics_gold_structural_composition' })
export class AnalyticsGoldStructuralComposition {
  @PrimaryColumn() country_code: string;
  @PrimaryColumn() year: number;

  @Column({ type: 'float', nullable: true, name: 'agri_va_share_actual' }) agri_va_share_actual: number;
  @Column({ type: 'float', nullable: true, name: 'agri_va_share_trend' }) agri_va_share_trend: number;
  @Column({ type: 'float', nullable: true, name: 'manuf_va_share_actual' }) manuf_va_share_actual: number;
  @Column({ type: 'float', nullable: true, name: 'manuf_va_share_trend' }) manuf_va_share_trend: number;
}