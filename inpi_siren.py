import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Dict, List
from zipfile import ZipFile

import requests
import os
import json
import networkx as nx
from pyvis.network import Network
from networkx.readwrite import json_graph

import logging
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)

class SocieteInpi:
    def __init__(
        self, user: str = "sem.eglohlokoh-portail-data", password: str = "DataInpi21", level: int = 1
    ):
        self.user = user
        self.password = password
        self.session = self.create_session_()
        self.ns = {"d": "fr:inpi:odrncs:imrSaisisTcXML"}
        self.siren = None
        self.unite_legales = []
        self.representants = []
        self.beneficiaires = []
        self.level = level
        
        self.net = Network('640px',"950px", directed=True)
        self.G = nx.DiGraph()
        
        logging.info('OHAYÔ GOZAIMASU. サイレンを鳴らさせてください ')

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
        if dossier.findall(
            "d:beneficiaires", self.ns
        ):  # and (date==derniere_immatriculation):
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

    def search_siren(self, siren: int, level: int = 1) -> Dict:

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
            
            to_return = {
                    "unite_legales": self.unite_legales,
                    "representants": self.representants,
                    "beneficaires": self.beneficiaires
                    }
            
            path = f'./AllDatabase/{self.siren}'
            if not os.path.exists(path):
                os.makedirs(path)
            json.dump(to_return,open(f'{path}/{self.siren}.json','w'))
            logging.info(f'DATA SAVED by JIRAYA AT {path}/{self.siren}.json')
            
            return to_return
            
        else:
            raise ValueError("Invalid SIREN")
            return {}        


    def add_nodes(self, unités_legale: dict, rep: dict, benef: dict) -> list: 

        rep_moral = []
        t =['form_jur' ,'activ_princip' ,'montant_cap']
        title = ' </br> '.join(f'{k}:{v}' for k,v in unités_legale.items() if k in t)
        self.G.add_node(unités_legale['denomination'], color = "red", weight=4, title = title )

        for elem in rep:
            if elem["type"] != "P.Physique":
                t =['qualite','form_jur' ,'siren' ,'adr_rep_pays']
                title = ' </br> '.join(f'{k}:{v}' for k,v in elem.items() if k in t)
                self.G.add_node(elem["denomination"], color = "chocolate", weight=1, title = title)
                rep_moral.append((elem["denomination"],elem['siren']))  # for self rep moraux
            else:
                name = elem["nom_patronymique"] +" "+ elem["prenoms"]
                t =['qualite','nationalite']
                title = ' </br> '.join(f'{k}:{v}' for k,v in elem.items() if k in t)
                self.G.add_node(name, color = "grey", weight=1, title = title)

        for elem in benef:
            name = elem["nom_naissance"] +" "+ elem["prenoms"]
            t =['detention_part_totale','date_naissance','nationalite']
            title = ' </br> '.join(f'{k}:{v}' for k,v in elem.items() if k in t)
            self.G.add_node(name, color = "grey", weight=1, title = title)

        return rep_moral


    def add_egdes(self, unités_legale: dict, rep: dict, benef: dict):

        for elem in rep:
            if elem["type"] != "P.Physique":
                self.G.add_edge(elem["denomination"], unités_legale['denomination'], color = "grey")
            else:
                name = elem["nom_patronymique"] +" "+ elem["prenoms"]
                self.G.add_edge(name, unités_legale['denomination'], color = "grey")

        for elem in benef:
            name = elem["nom_naissance"] +" "+ elem["prenoms"]
            self.G.add_edge(name, unités_legale['denomination'], color = "green")


    def visualize_siren(self, siren :int):
        res = self.search_siren(siren)

        if len(res)>0:
            logging.info(f'VISUALISING {self.siren}')

            unités_legale = self.unite_legales[0][0]
            rep = self.representants[0]
            benef = self.beneficiaires[0]

            self.rep_moral = self.add_nodes(unités_legale, rep, benef)
            self.add_egdes(unités_legale, rep, benef)

            if self.level>1 and len(self.rep_moral)>=1:
                # actual = 
                for p_moral in self.rep_moral:
                    res = self.search_siren(int(p_moral[1]))
                    unités_legale = res['unite_legales'][0][0]
                    rep = res['representants'][0]
                    benef = res['beneficaires'][0]

                    rep_moral_2 = self.add_nodes(unités_legale, rep, benef)
                    self.add_egdes(unités_legale, rep, benef)

            self.net.from_nx(self.G)                        
            path = f'./AllDatabase/{self.siren}'

            if not os.path.exists(path):
                os.makedirs(path)
                
            self.net.show(f'{path}/{self.siren}.html')
            json.dump(json_graph.node_link_data(self.G),open(f'{path}/graph.json','w'))
            
            logging.info(f'GRAPH SAVED by JIRAYA AT {path}')
            self.G.clear()

        else:
            logging.info(f'NO DAAAAAATAAAAAAAAAA {self.siren}')
            


def main():
    inpi = SocieteInpi() # mettre votre password avec password= et user avec user=
    res = inpi.search_siren(791012081)
    print(res)


if __name__ == "__main__":
    main()