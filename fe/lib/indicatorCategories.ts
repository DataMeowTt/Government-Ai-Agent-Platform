export const INDICATOR_CATEGORY_LABELS: Record<string, string> = {
  growth_dynamics: 'Tăng trưởng và quy mô nền kinh tế',
  fiscal_monetary: 'Tài khóa và tiền tệ',
  crisis_risk: 'Rủi ro khủng hoảng và ổn định vĩ mô',
  social_welfare: 'Phúc lợi xã hội và thị trường lao động',
  structural_composition: 'Cơ cấu kinh tế và chuyển dịch ngành',
};

export function getIndicatorCategoryLabel(category?: string | null): string {
  if (!category) return 'Khác';
  return INDICATOR_CATEGORY_LABELS[category] || category;
}
