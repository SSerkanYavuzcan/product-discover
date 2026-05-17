from pydantic import BaseModel


class NutritionFacts(BaseModel):
    per: str = "100g"
    energy_kcal: float | None = None
    fat_g: float | None = None
    saturated_fat_g: float | None = None
    carbohydrates_g: float | None = None
    sugars_g: float | None = None
    protein_g: float | None = None
    salt_g: float | None = None
    fiber_g: float | None = None
