import { create } from 'zustand';

interface FilterState {
  selectedCountry: string;
  anomalyThreshold: number;
  setSelectedCountry: (country: string) => void;
  setAnomalyThreshold: (threshold: number) => void;
}

export const useFilterStore = create<FilterState>((set) => ({
  selectedCountry: '',
  anomalyThreshold: 0.75,
  setSelectedCountry: (country) => set({ selectedCountry: country }),
  setAnomalyThreshold: (threshold) => set({ anomalyThreshold: threshold }),
}));