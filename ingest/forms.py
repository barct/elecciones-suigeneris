from django import forms

from elections.models import District, List


class SelectionForm(forms.Form):
    district = forms.ModelChoiceField(
        queryset=District.objects.order_by("name"),
        label="Distrito",
    )
    chamber = forms.ChoiceField(
        choices=List.Chamber.choices,
        label="Cámara",
        initial=List.Chamber.DEPUTIES,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["district"].empty_label = "Seleccione un distrito"


class ScrutinyForm(forms.Form):
    percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
        label="%",
        help_text="Ingrese el porcentaje obtenido por la lista",
    )

    def clean_percentage(self):
        value = self.cleaned_data.get("percentage")
        if value == "":
            return None
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["percentage"].widget.attrs.update(
            {
                "class": "form-control text-right",
                "placeholder": "0.00",
                "step": "0.01",
            }
        )
