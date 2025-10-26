from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class District(models.Model):
	name = models.CharField(max_length=120, unique=True)
	renewal_seats = models.PositiveSmallIntegerField(help_text="Bancas que se renuevan en 2025")
	total_deputies = models.PositiveSmallIntegerField(help_text="Total de diputadas y diputados del distrito")
	registered_voters = models.PositiveIntegerField(help_text="Cantidad de electores habilitados")
	senator_renewal_seats = models.PositiveSmallIntegerField(
		default=0,
		help_text="Bancas de senadores nacionales que se renuevan",
	)
	total_senators = models.PositiveSmallIntegerField(
		default=0,
		help_text="Total de senadoras y senadores del distrito",
	)

	class Meta:
		ordering = ["name"]

	def __str__(self) -> str:
		return self.name


class List(models.Model):
	class Chamber(models.TextChoices):
		DEPUTIES = "diputados", "Diputados"
		SENATORS = "senadores", "Senadores"

	district = models.ForeignKey(
		District,
		on_delete=models.CASCADE,
		related_name="lists",
	)
	chamber = models.CharField(
		max_length=15,
		choices=Chamber.choices,
		default=Chamber.DEPUTIES,
		help_text="Cámara para la que se presenta la lista",
	)
	order = models.PositiveSmallIntegerField(
		help_text="Posición en la boleta o prioridad de exhibición",
		default=0,
	)
	code = models.CharField(max_length=20)
	name = models.CharField(max_length=150)
	national_alignment = models.CharField(
		max_length=150,
		blank=True,
		help_text="Denominación de la fuerza a nivel nacional",
	)

	class Meta:
		ordering = ["district__name", "chamber", "order", "code"]
		unique_together = ("district", "chamber", "code")

	def __str__(self) -> str:
		return f"{self.code} - {self.name} ({self.get_chamber_display()})"


class Scrutiny(models.Model):
	election_list = models.ForeignKey(
		List,
		on_delete=models.CASCADE,
		related_name="scrutiny_records",
	)
	percentage = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		validators=[MinValueValidator(0), MaxValueValidator(100)],
		help_text="Porcentaje del escrutinio provisorio",
	)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]

	def __str__(self) -> str:
		return f"{self.election_list.code} {self.percentage}%"
