// Клиентская копия проверки ИИН/БИН (backend/app/schemas/legal.py::is_valid_kz_id)
// для мгновенной подсказки в форме. Источник истины — бэкенд.

const WEIGHTS_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] as const;
const WEIGHTS_2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2] as const;

function weightedMod11(digits: number[], weights: readonly number[]): number {
  let sum = 0;
  for (let i = 0; i < 11; i++) sum += (digits[i] ?? 0) * (weights[i] ?? 0);
  return sum % 11;
}

export function isValidKzId(value: string): boolean {
  if (!/^\d{12}$/.test(value)) return false;
  const digits = [...value].map(Number);
  let control = weightedMod11(digits, WEIGHTS_1);
  if (control === 10) {
    control = weightedMod11(digits, WEIGHTS_2);
    if (control === 10) return false;
  }
  return control === digits[11];
}
