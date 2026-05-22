import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'gold_structural_composition' })
export class GoldStructuralComposition {
  @PrimaryColumn({ type: 'varchar', length: 3 })
  country_code: string;

  @PrimaryColumn({ type: 'int' })
  year: number;

  @Column({ type: 'text' })
  country: string;

  @Column({ type: 'float', nullable: true })
  decade: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_value' })
  GDP_value: number | null;

  @Column({ type: 'float', nullable: true, name: 'GFCF_value' })
  GFCF_value: number | null;

  @Column({ type: 'float', nullable: true, name: 'GNI_value' })
  GNI_value: number | null;

  @Column({ type: 'float', nullable: true, name: 'Agri_VA' })
  Agri_VA: number | null;

  @Column({ type: 'float', nullable: true, name: 'Manuf_VA' })
  Manuf_VA: number | null;

  @Column({ type: 'float', nullable: true, name: 'VA_FoodBev' })
  VA_FoodBev: number | null;

  @Column({ type: 'float', nullable: true, name: 'GFCF_to_GDP' })
  GFCF_to_GDP: number | null;

  @Column({ type: 'float', nullable: true, name: 'GNI_to_GDP' })
  GNI_to_GDP: number | null;

  @Column({ type: 'float', nullable: true })
  agri_va_share: number | null;

  @Column({ type: 'float', nullable: true })
  manuf_va_share: number | null;

  @Column({ type: 'float', nullable: true })
  food_bev_share_manuf: number | null;

  @Column({ type: 'float', nullable: true, name: 'GDP_growth_YoY' })
  GDP_growth_YoY: number | null;

  @Column({ type: 'float', nullable: true })
  flag_score: number | null;

  @Column({ type: 'text', nullable: true })
  income_group: string | null;

  @Column({ type: 'text', nullable: true })
  development_group: string | null;

  @Column({ type: 'float' })
  completeness_score: number;
}