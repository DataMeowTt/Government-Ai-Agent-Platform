import {
  BadRequestException,
  Injectable,
  InternalServerErrorException,
  Optional,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { BigQueryService } from '../bigquery/bigquery.service';
import { getIndicator } from '../generated/indicator-contract';
import { GoldGrowthDynamics } from '../entities/gold-growth-dynamics.entity';

type CompareRow = {
  country_code: string;
  country: string;
  year: number;
  indicator: string;
  indicator_name: string;
  category: string;
  unit: string;
  value: number | null;
};

@Injectable()
export class CompareService {
  constructor(
    private readonly configService: ConfigService,
    private readonly bigQueryService: BigQueryService,
    @Optional()
    @InjectRepository(GoldGrowthDynamics)
    private readonly growthRepo?: Repository<GoldGrowthDynamics>,
  ) {}

  async compare(
    countries: string[],
    indicatorCode: string,
    from?: number,
    to?: number,
  ): Promise<CompareRow[]> {
    const indicator = this.getComparableIndicatorOrThrow(indicatorCode);
    const normalizedCountries = Array.from(
      new Set(
        (countries || [])
          .map(code => this.normalizeCountryCode(code))
          .filter((code): code is string => Boolean(code)),
      ),
    );

    if (normalizedCountries.length === 0) {
      throw new BadRequestException(
        'Danh sách quốc gia rỗng hoặc không hợp lệ. Yêu cầu mã ISO3.',
      );
    }

    const fromYear = this.parseYear(from);
    const toYear = this.parseYear(to);
    const [safeFrom, safeTo] =
      fromYear != null && toYear != null && fromYear > toYear
        ? [toYear, fromYear]
        : [fromYear, toYear];

    if (this.isBigQueryMode()) {
      return this.bigQueryService.getCompareRows({
        countries: normalizedCountries,
        indicator: indicator.code,
        from: safeFrom ?? undefined,
        to: safeTo ?? undefined,
      });
    }

    const growthRepo = this.getGrowthRepo();
    const safeTable = this.ensureSafeIdentifier(indicator.gold_table as string);
    const safeColumn = this.ensureSafeIdentifier(indicator.gold_column);
    const indicatorName = indicator.name_vi || indicator.name_en || indicator.code;

    const clauses: string[] = ['country_code = ANY($1)'];
    const params: Array<string[] | number | string | null> = [normalizedCountries];
    if (safeFrom != null) {
      clauses.push(`year >= $${params.length + 1}`);
      params.push(safeFrom);
    }
    if (safeTo != null) {
      clauses.push(`year <= $${params.length + 1}`);
      params.push(safeTo);
    }

    const sql = `
      SELECT
        country_code,
        COALESCE(country, country_code) AS country,
        year,
        $${params.length + 1}::text AS indicator,
        $${params.length + 2}::text AS indicator_name,
        $${params.length + 3}::text AS category,
        $${params.length + 4}::text AS unit,
        "${safeColumn}" AS value
      FROM "${safeTable}"
      WHERE ${clauses.join(' AND ')}
      ORDER BY year ASC, country_code ASC
      LIMIT 2000
    `;
    params.push(
      indicator.code,
      indicatorName,
      indicator.category,
      indicator.unit || '',
    );

    const rows = await growthRepo.query(sql, params);
    return rows.map((row: Record<string, unknown>) => ({
      country_code: String(row.country_code),
      country: String(row.country || row.country_code),
      year: Number(row.year),
      indicator: String(row.indicator),
      indicator_name: String(row.indicator_name),
      category: String(row.category),
      unit: String(row.unit),
      value:
        row.value == null || Number.isNaN(Number(row.value))
          ? null
          : Number(row.value),
    }));
  }

  private isBigQueryMode(): boolean {
    return this.configService.get<string>('BACKEND_DATA_SOURCE') === 'bigquery';
  }

  private getComparableIndicatorOrThrow(indicatorCode: string) {
    const indicator = getIndicator(indicatorCode);
    if (!indicator) {
      throw new BadRequestException(`Chỉ số không tồn tại: ${indicatorCode}`);
    }
    if (
      !indicator.supports_compare ||
      !indicator.supports_raw ||
      !indicator.gold_table ||
      !indicator.gold_column
    ) {
      throw new BadRequestException(
        `Chỉ số ${indicatorCode} chưa hỗ trợ so sánh theo contract hiện tại.`,
      );
    }
    return indicator;
  }

  private normalizeCountryCode(countryCode?: string): string | undefined {
    if (!countryCode) {
      return undefined;
    }
    const normalized = countryCode.trim().toUpperCase();
    return /^[A-Z]{3}$/.test(normalized) ? normalized : undefined;
  }

  private parseYear(value?: number): number | null {
    if (value == null) {
      return null;
    }
    const year = Number(value);
    if (!Number.isFinite(year)) {
      return null;
    }
    return Math.trunc(year);
  }

  private ensureSafeIdentifier(input: string): string {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(input)) {
      throw new BadRequestException(`Định danh SQL không hợp lệ: ${input}`);
    }
    return input;
  }

  private getGrowthRepo(): Repository<GoldGrowthDynamics> {
    if (!this.growthRepo) {
      throw new InternalServerErrorException(
        'PostgreSQL repository unavailable: GoldGrowthDynamics repository is not configured.',
      );
    }
    return this.growthRepo;
  }
}
