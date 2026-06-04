"""Municipality rules shared across app."""

from __future__ import annotations


MUNICIPALITIES_WITHOUT_NATURE = frozenset(
    {
        "Acerra",
        "Afragola",
        "Arzano",
        "Aversa",
        "Bellizzi",
        "Boscoreale",
        "Brusciano",
        "Caivano",
        "Calvizzano",
        "Camposano",
        "Capodrise",
        "Cardito",
        "Carinaro",
        "Casagiove",
        "Casal di Principe",
        "Casalnuovo di Napoli",
        "Casaluce",
        "Casandrino",
        "Casapesenna",
        "Casapulla",
        "Casavatore",
        "Casoria",
        "Castello di Cisterna",
        "Cercola",
        "Cesa",
        "Cicciano",
        "Cimitile",
        "Comiziano",
        "Crispano",
        "Curti",
        "Frattamaggiore",
        "Frattaminore",
        "Frignano",
        "Gricignano di Aversa",
        "Grumo Nevano",
        "Liveri",
        "Lusciano",
        "Macerata Campania",
        "Marcianise",
        "Mariglianella",
        "Marigliano",
        "Marzano di Nola",
        "Melito di Napoli",
        "Mugnano di Napoli",
        "Nola",
        "Orta di Atella",
        "Pastorano",
        "Poggiomarino",
        "Pomigliano d'Arco",
        "Pompei",
        "Portico di Caserta",
        "Qualiano",
        "Recale",
        "San Cipriano d'Aversa",
        "San Gennaro Vesuviano",
        "San Giorgio a Cremano",
        "San Marcellino",
        "San Marco Evangelista",
        "San Marzano sul Sarno",
        "San Nicola la Strada",
        "San Paolo Bel Sito",
        "San Tammaro",
        "San Valentino Torio",
        "San Vitaliano",
        "Sant'Antimo",
        "Sant'Arpino",
        "Santa Maria Capua Vetere",
        "Santa Maria la Carita",
        "Saviano",
        "Scafati",
        "Scisciano",
        "Sparanise",
        "Striano",
        "Succivo",
        "Teverola",
        "Torre Annunziata",
        "Trentola-Ducenta",
        "Tufino",
        "Villa Literno",
        "Villa di Briano",
        "Volla",
    }
)


def filter_municipalities_with_nature(names: list[str]) -> list[str]:
    """Keep stable, unique municipality list with supported nature data."""

    seen: set[str] = set()
    filtered: list[str] = []

    for name in names:
        if not name or name in MUNICIPALITIES_WITHOUT_NATURE or name in seen:
            continue

        seen.add(name)
        filtered.append(name)

    return filtered
