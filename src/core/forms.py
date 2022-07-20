from django import forms


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label="CSV-файл")
