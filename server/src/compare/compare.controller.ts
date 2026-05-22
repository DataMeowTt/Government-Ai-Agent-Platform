import {
  BadRequestException,
  Controller,
  Get,
  Query,
} from '@nestjs/common';
import { CompareService } from './compare.service';

@Controller('api/v1/compare')
export class CompareController {
  constructor(private readonly compareService: CompareService) {}

  @Get()
  async compare(
    @Query('countries') countriesRaw: string,
    @Query('indicator') indicator: string,
    @Query('from') fromRaw?: string,
    @Query('to') toRaw?: string,
  ) {
    if (!countriesRaw) {
      throw new BadRequestException(
        'Thiếu tham số countries. Ví dụ: countries=VNM,THA',
      );
    }
    if (!indicator) {
      throw new BadRequestException('Thiếu tham số indicator.');
    }

    const countries = countriesRaw
      .split(',')
      .map(value => value.trim())
      .filter(Boolean);

    return this.compareService.compare(
      countries,
      indicator,
      this.parseYearOrUndefined(fromRaw),
      this.parseYearOrUndefined(toRaw),
    );
  }

  private parseYearOrUndefined(raw?: string): number | undefined {
    if (raw == null || raw.trim() === '') {
      return undefined;
    }
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      throw new BadRequestException(`Năm không hợp lệ: ${raw}`);
    }
    return Math.trunc(parsed);
  }
}
