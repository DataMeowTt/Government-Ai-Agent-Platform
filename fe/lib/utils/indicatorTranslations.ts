export const INDICATOR_VI_NAMES: Record<string, string> = {
  // Growth
  rGDP_growth_YoY: 'Tăng trưởng GDP thực',
  rolling_mean_5yr: 'Trung bình trượt 5 năm',
  GDP_growth_YoY: 'Tăng trưởng GDP danh nghĩa',
  GDP_growth_trend_5yr: 'Xu hướng tăng trưởng 5 năm',
  trend_deviation: 'Độ lệch xu hướng',
  GDP_pc_growth_gap: 'Chênh lệch GDP bình quân',
  log_rGDP_pc_USD: 'Log GDP thực bình quân',
  
  // Fiscal
  govdebt_GDP: 'Nợ công / GDP',
  debt_change_YoY: 'Biến động nợ công',
  govrev_GDP: 'Thu ngân sách / GDP',
  govexp_GDP: 'Chi ngân sách / GDP',
  fiscal_balance_GDP: 'Cân đối ngân sách / GDP',
  cumulative_deficit_5yr: 'Thâm hụt tích lũy 5 năm',
  tax_revenue_pct_GDP: 'Thu thuế / GDP',
  
  // Monetary
  ltrate: 'Lãi suất dài hạn',
  infl: 'Lạm phát (GDP Deflator)',
  real_interest_rate: 'Lãi suất thực',
  inflation_cpi: 'Lạm phát CPI',
  inflation_deflator: 'Lạm phát GDP Deflator',
  inflation_gap: 'Chênh lệch lạm phát',
  rolling_3yr_avg_cpi: 'Trung bình CPI 3 năm',
  
  // Risk
  SovDebtCrisis: 'Khủng hoảng nợ công',
  CurrencyCrisis: 'Khủng hoảng tiền tệ',
  BankingCrisis: 'Khủng hoảng ngân hàng',
  crisis_composite: 'Chỉ số khủng hoảng tổng hợp',
  crisis_any: 'Có khủng hoảng',
  REER_deviation: 'Độ lệch tỷ giá REER',
  spending_efficiency: 'Hiệu quả chi tiêu công',
  
  // Social
  unemployment_total: 'Tỷ lệ thất nghiệp',
  unemployment_youth: 'Thất nghiệp thanh niên',
  youth_unemployment_gap: 'Chênh lệch thất nghiệp thanh niên',
  youth_gap_ratio: 'Tỷ lệ thất nghiệp thanh niên',
  self_employed_pct: 'Lao động tự doanh',
  poverty_headcount: 'Tỷ lệ nghèo',
  poverty_change_5yr: 'Biến động nghèo 5 năm',
  hcons_share: 'Tiêu dùng hộ gia đình / GDP',
  hcons_growth: 'Tăng trưởng tiêu dùng',
  trade_pct_gdp: 'Thương mại / GDP',
  
  // Demographics
  urban_pop_pct: 'Dân số đô thị (%)',
  urban_pop_growth: 'Tăng dân số đô thị',
  pop_density: 'Mật độ dân số',
  log_pop_density: 'Log mật độ dân số',
  pop_growth: 'Tăng dân số',
  
  // Structure
  decade: 'Thập kỷ',
  GDP_value: 'GDP (USD)',
  GFCF_value: 'Đầu tư tài sản cố định (USD)',
  GNI_value: 'GNI (USD)',
  Agri_VA: 'Nông nghiệp (USD)',
  Manuf_VA: 'Công nghiệp chế biến (USD)',
  VA_FoodBev: 'Thực phẩm & đồ uống (USD)',
  GFCF_to_GDP: 'Đầu tư tài sản cố định / GDP',
  GNI_to_GDP: 'GNI / GDP',
  agri_va_share: 'Tỷ trọng nông nghiệp',
  manuf_va_share: 'Tỷ trọng công nghiệp chế biến',
  food_bev_share_manuf: 'Thực phẩm & đồ uống / Công nghiệp',
  flag_score: 'Điểm chất lượng dữ liệu',
};

export const getIndicatorViName = (code: string): string => {
  return INDICATOR_VI_NAMES[code] || code;
};