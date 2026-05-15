import { Injectable } from '@nestjs/common';
import {
  GeneratedIndicatorContract,
  listIndicators,
  getIndicator,
} from '../generated/indicator-contract';

export interface Indicator {
  code: string;
  name: string;
  name_vi: string;
  name_en: string;
  category: string;
  unit: string;
  table: string;
  gold_table: string | null;
  gold_column: string;
  analytics_table: string | null;
  supports_raw: boolean;
  supports_compare: boolean;
  supports_ranking: boolean;
  supports_coverage: boolean;
  supports_trend: boolean;
  supports_anomaly: boolean;
  used_for_cluster: boolean;
  description_vi: string;
  description_en: string;
  aliases: readonly string[];
}

function toIndicator(contract: GeneratedIndicatorContract): Indicator {
  return {
    code: contract.code,
    name: contract.name_en || contract.name_vi || contract.code,
    name_vi: contract.name_vi,
    name_en: contract.name_en,
    category: contract.category,
    unit: contract.unit,
    table: contract.gold_table ?? '',
    gold_table: contract.gold_table,
    gold_column: contract.gold_column,
    analytics_table: contract.analytics_table,
    supports_raw: contract.supports_raw,
    supports_compare: contract.supports_compare,
    supports_ranking: contract.supports_ranking,
    supports_coverage: contract.supports_coverage,
    supports_trend: contract.supports_trend,
    supports_anomaly: contract.supports_anomaly,
    used_for_cluster: contract.used_for_cluster,
    description_vi: contract.description_vi,
    description_en: contract.description_en,
    aliases: contract.aliases,
  };
}

@Injectable()
export class IndicatorsService {
  private readonly indicators: Indicator[] = listIndicators()
    .map(toIndicator)
    .sort((a, b) => a.code.localeCompare(b.code));

  findAll(): Indicator[] {
    return this.indicators;
  }

  findByCategory(category: string): Indicator[] {
    const normalizedCategory = category.trim().toLowerCase();

    return this.indicators.filter(
      indicator => indicator.category.toLowerCase() === normalizedCategory,
    );
  }

  findByCode(code: string): Indicator | undefined {
    const contract = getIndicator(code);

    return contract ? toIndicator(contract) : undefined;
  }
}