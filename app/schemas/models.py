"""Tortoise-ORM 数据模型。"""
from __future__ import annotations

from tortoise import fields, models


class UserProfileModel(models.Model):
    user_id = fields.CharField(pk=True, max_length=64)
    age = fields.IntField(null=True)
    gender = fields.CharField(max_length=8, null=True)
    height_cm = fields.FloatField(null=True)
    weight_kg = fields.FloatField(null=True)
    bmi = fields.FloatField(null=True)
    chronic_diseases = fields.JSONField(default=list)
    allergies = fields.JSONField(default=list)
    diet_preferences = fields.JSONField(default=list)
    budget_per_day = fields.FloatField(null=True)
    pregnancy = fields.BooleanField(default=False)
    medications = fields.JSONField(default=list)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_profile"

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "age": self.age,
            "gender": self.gender,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "bmi": self.bmi,
            "chronic_diseases": self.chronic_diseases or [],
            "allergies": self.allergies or [],
            "diet_preferences": self.diet_preferences or [],
            "budget_per_day": self.budget_per_day,
            "pregnancy": self.pregnancy,
            "medications": self.medications or [],
        }

    @classmethod
    async def upsert_from_dict(cls, data: dict) -> UserProfileModel:
        # 注意:不能叫 update_from_dict —— 那会覆盖 tortoise 内置的同名实例方法,
        # 导致 update_or_create 在更新已存在行时调用到这个 async classmethod 而崩溃。
        user_id = data["user_id"]
        clean = {
            k: v
            for k, v in data.items()
            if k in {f.model_field_name for f in cls._meta.fields_map.values()}
            and k != "user_id"
        }
        obj, _ = await cls.update_or_create(user_id=user_id, defaults=clean)
        return obj


class ScreeningRecord(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=64, index=True)
    total_score = fields.IntField()
    risk_level = fields.CharField(max_length=32)
    pdf_object_key = fields.CharField(max_length=255, null=True)
    payload = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "screening_record"


class MealPlanRecord(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=64, index=True)
    plan_id = fields.CharField(max_length=64, index=True)
    target_kcal = fields.FloatField()
    pdf_object_key = fields.CharField(max_length=255, null=True)
    payload = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "meal_plan_record"


class DailyIntake(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=64, index=True)
    date = fields.DateField(index=True)
    kcal = fields.FloatField(default=0)
    protein = fields.FloatField(default=0)
    carb = fields.FloatField(default=0)
    fat = fields.FloatField(default=0)
    water_ml = fields.FloatField(default=0)

    class Meta:
        table = "daily_intake"
        unique_together = (("user_id", "date"),)


class Vitals(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=64, index=True)
    date = fields.DateField(index=True)
    weight_kg = fields.FloatField(null=True)
    steps = fields.IntField(default=0)
    sleep_hours = fields.FloatField(null=True)

    class Meta:
        table = "vitals"


class AuditLog(models.Model):
    id = fields.IntField(pk=True)
    request_id = fields.CharField(max_length=64, index=True)
    user_id = fields.CharField(max_length=64, index=True)
    action = fields.CharField(max_length=64)
    payload = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "audit_log"
