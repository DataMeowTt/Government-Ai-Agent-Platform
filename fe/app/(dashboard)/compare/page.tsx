'use client';
import { useState } from 'react';
import MultiCountrySelector from '@/components/filters/MultiCountrySelector';
import IndicatorSelector from '@/components/filters/IndicatorSelector';
import CompareLineChart from '@/components/charts/CompareLineChart';
import { useCompare } from '@/lib/hooks/useCompare';

export default function ComparePage() {
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedIndicator, setSelectedIndicator] = useState('rGDP_growth_YoY');
  const { data, isLoading, error } = useCompare(selectedCountries, selectedIndicator);

  const getIndicatorName = (code: string) => {
    const names: Record<string, string> = {
      rGDP_growth_YoY: 'Real GDP Growth (%)',
      govdebt_GDP: 'Government Debt (% GDP)',
      REER_deviation: 'REER Deviation (%)',
      inflation_cpi: 'Inflation (CPI)',
      poverty_headcount: 'Poverty Headcount (%)',
      unemployment_total: 'Unemployment (%)',
      manuf_va_share: 'Manufacturing Value Added (% GDP)',
      agri_va_share: 'Agriculture Value Added (% GDP)',
    };
    return names[code] || code;
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Compare Countries</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div>
          <label className="block font-medium mb-2">Select Countries (max 5)</label>
          <MultiCountrySelector selected={selectedCountries} onChange={setSelectedCountries} max={5} />
        </div>
        <div>
          <label className="block font-medium mb-2">Select Indicator</label>
          <IndicatorSelector selected={selectedIndicator} onChange={setSelectedIndicator} />
        </div>
      </div>
      {selectedCountries.length === 0 && (
        <div className="bg-yellow-50 p-4 rounded text-yellow-800">Please select at least one country.</div>
      )}
      {isLoading && <div>Loading comparison data...</div>}
      {error && <div>Error: {error.message}</div>}
      {!isLoading && !error && selectedCountries.length > 0 && (
        <div className="bg-white p-4 rounded shadow">
          <h2 className="text-lg font-semibold mb-2">{getIndicatorName(selectedIndicator)}</h2>
          <CompareLineChart data={data} indicatorName={getIndicatorName(selectedIndicator)} />
        </div>
      )}
    </div>
  );
}