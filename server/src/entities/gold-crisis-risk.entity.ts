import { Entity, Column, PrimaryColumn } from 'typeorm';

@Entity({ name: 'gold_crisis_risk' })
export class GoldCrisisRisk {
  @PrimaryColumn({ type: 'varchar', length: 3 })
  country_code: string;

  @PrimaryColumn({ type: 'int' })
  year: number;

  @Column({ type: 'text' })
  country: string;

  @Column({ type: 'smallint', nullable: true, name: 'SovDebtCrisis' })
  SovDebtCrisis: number | null;

  @Column({ type: 'smallint', nullable: true, name: 'CurrencyCrisis' })
  CurrencyCrisis: number | null;

  @Column({ type: 'smallint', nullable: true, name: 'BankingCrisis' })
  BankingCrisis: number | null;

  @Column({ type: 'smallint', nullable: true })
  crisis_composite: number | null;

  @Column({ type: 'smallint', nullable: true })
  crisis_any: number | null;

  @Column({ type: 'float', nullable: true, name: 'REER_deviation' })
  REER_deviation: number | null;

  @Column({ type: 'float', nullable: true })
  spending_efficiency: number | null;

  @Column({ type: 'float', nullable: true, name: 'govdebt_GDP' })
  govdebt_GDP: number | null;

  @Column({ type: 'float', nullable: true, name: 'fiscal_balance_GDP' })
  fiscal_balance_GDP: number | null;

  @Column({ type: 'float', nullable: true, name: 'rGDP_growth_YoY' })
  rGDP_growth_YoY: number | null;

  @Column({ type: 'text', nullable: true })
  income_group: string | null;

  @Column({ type: 'text', nullable: true })
  development_group: string | null;

  @Column({ type: 'float' })
  completeness_score: number;
}