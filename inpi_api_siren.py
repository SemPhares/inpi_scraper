import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Dict, List
from zipfile import ZipFile

import requests


class SocieteInpi:
    def __init__(self, user: str = "bsanchot-portail-data", password: str = ""):
        self.user = user
        self.password = password
        self.session = self.create_session_()
        self.ns = {"d": "fr:inpi:odrncs:imrSaisisTcXML"}
        self.siren = None
        self.unite_legales = []
        self.representants = []
        self.beneficiaires = []

    def create_session_(self) -> object:
        s = requests.session()
        headers_dict = {"login": self.user, "password": self.password}
        s.post(
            "https://opendata-rncs.inpi.fr/services/diffusion/login",
            headers=headers_dict,
        )
        return s

    def get_zip_(self, res) -> object:
        zipfile = BytesIO(res.content)
        files = ZipFile(zipfile)
        filenames = files.namelist()
        if any(".zip" in file for file in filenames):
            zipfile = files.open(filenames[0])
            inside_zip = ZipFile(zipfile)
        else:
            raise ValueError("No zip found for provided SIREN")
        return inside_zip

    def get_unite_legale_(self, tree) -> List[List[Dict]]:
        identite_pm = tree.findall("d:dossier/d:identite/d:identite_PM", self.ns)
        if len(identite_pm) > 0:
            elems = [list(elem.iter()) for elem in identite_pm]
            unite_legale = [
                {
                    a.tag.replace("{fr:inpi:odrncs:imrSaisisTcXML}", ""): a.text
                    for a in b
                }
                for b in elems
            ]
        else:
            unite_legale = []
        return unite_legale

    def get_last_immat_(self, tree) -> int:
        dates = [
            int(date.text)
            for date in tree.findall("d:dossier/d:identite/d:dat_immat", self.ns)
        ]
        derniere_immatriculation = max(dates)
        return derniere_immatriculation

    def get_representants_(self, dossier) -> List[List[Dict]]:
        if dossier.findall(
            "d:representants", self.ns
        ):  # and (date==derniere_immatriculation):
            representants = dossier.findall("d:representants/d:representant", self.ns)
            elems = [list(elem.iter()) for elem in representants]
            representants = [
                {
                    a.tag.replace("{fr:inpi:odrncs:imrSaisisTcXML}", ""): a.text
                    for a in b
                }
                for b in elems
            ]
        else:
            representants = []

        return representants

    def get_beneficiaires_(self, dossier) -> List[List[Dict]]:
        if dossier.findall("d:beneficiaires", self.ns):
            # and (date==derniere_immatriculation):
            beneficiaires = dossier.findall("d:beneficiaires/d:beneficiaire", self.ns)
            elems = [list(elem.iter()) for elem in beneficiaires]
            beneficiaires = [
                {
                    a.tag.replace("{fr:inpi:odrncs:imrSaisisTcXML}", ""): a.text
                    for a in b
                }
                for b in elems
            ]

        else:
            beneficiaires = []

        return beneficiaires

    def check_siren_(self, siren: int) -> bool:
        if len(str(siren)) != 9:
            return False
        else:
            return True

    def search_siren(self, siren: int) -> Dict:

        self.unite_legales = []
        self.representants = []
        self.beneficiaires = []

        if self.check_siren_(siren):
            self.siren = siren
            res = self.session.get(
                f"https://opendata-rncs.inpi.fr/services/diffusion/imrs-saisis/get?listeSirens={siren}"
            )
            zips = self.get_zip_(res)
            tree = ET.fromstring(zips.open(zips.namelist()[0]).read())

            self.unite_legales.append(self.get_unite_legale_(tree))
            dossiers = tree.findall("d:dossier", self.ns)
            for dossier in dossiers:
                self.representants.append(self.get_representants_(dossier))
                self.beneficiaires.append(self.get_beneficiaires_(dossier))
        else:
            raise ValueError("Invalid SIREN")
        return {
            "unite_legales": self.unite_legales,
            "representants": self.representants,
            "beneficaires": self.beneficiaires,
        }


def main():
    inpi = SocieteInpi()  # mettre votre password avec password= et user avec user=
    res = inpi.search_siren(791012081)
    print(res)


if __name__ == "__main__":
    main()
