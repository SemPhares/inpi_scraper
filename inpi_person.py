import os
import re
import json
import time
import logging
import requests
import datetime
import itertools
import unicodedata
import networkx as nx
import ipywidgets as widgets
from random import randint
from fuzzywuzzy import fuzz
from ipywidgets import interact
from pyvis.network import Network
from fake_useragent import UserAgent
from matplotlib import pyplot as plt
from networkx.readwrite import json_graph
from tenacity import retry, stop_after_attempt

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import socket
from urllib3.connection import HTTPConnection
HTTPConnection.default_socket_options = (
HTTPConnection.default_socket_options + [
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        (socket.SOL_TCP, socket.TCP_KEEPIDLE, 45),
        (socket.SOL_TCP, socket.TCP_KEEPINTVL, 10),
        (socket.SOL_TCP, socket.TCP_KEEPCNT, 6)
    ]
)

import warnings
warnings.filterwarnings(action='ignore')

ua = UserAgent()
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%d/%m/%Y %I:%M:%S %p', level=logging.INFO)

class Inpi_person:
    """
    Class used to make connexion with Inpi elasticsearch database and mke a json file of database based on a query
    """
#     ua = UserAgent()
    def __init__(self,query:str,mm_aaaa:str):
        self.query = query
        self.mm_aaaa = mm_aaaa
        self.random_ua = ua.random
        self.retry_strategy = Retry(
                                    total=3,
                                    status_forcelist=[429, 500, 502, 503, 504],
                                    method_whitelist=["HEAD", "GET", "OPTIONS", "POST"]
                                )

    def normalize_(self,text:str):
        """
        Treat inputed text by removing accent, removing punctuation and capitalize
        text: input text
        """
        
        #strip_accents
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                      if unicodedata.category(c) != 'Mn')
        #strip_punctiation
        text = re.sub('[^a-zA-Z\s-]','',text)
        #captalize
        text = " ".join(__.capitalize() for __ in text.split(" "))
        return text

    def jaccard_text_similarity(self,text_1:str, text_2:str):
        """
        This function take two text and return the jaccard similarity
        text_1 : input text 1
        text_2 : input text 2
        """
        t1 = text_1.split(" ")
        t2 = text_2.split(" ")
        text_1_inter_text_2 = len(list(set(t1) & set(t2)))
        return float(text_1_inter_text_2)/float(len(list(set(t1+t2))))

    def get_millisec(self,date: str):
        """
        Transform date in format '%m/%Y' to milliseconds in int type
        """
        return int(datetime.datetime.strptime(date,'%m/%Y').timestamp())*1000

    def get_date_from_millisec(self,date):
        """
        Transform date in format milliseconds to date '%m/%Y' format
        """
        return datetime.datetime.fromtimestamp(int(date)/1000).strftime('%m/%Y')
    
    @retry(stop=stop_after_attempt(7))
    def search_inpi(self):
        """
        Use init params to grab data from INPI's elasticsearch database.
        adapter is used to avoid error when the database is not reacheable 
        """
        adapter = HTTPAdapter(max_retries=self.retry_strategy)
        http = requests.Session()
        URL = "https://data.inpi.fr/search"
        req =     {"query":{"searchField":[],"type":"companies","selectedIds":[],
                            "sort":"relevance","order":"asc","nbResultsPerPage":"800","page":"1","filter":{},"q":f"'{self.query}'"},"aggregations":["idt_cp_short","idt_pm_form_jur"]}
        header = {'User-Agent': self.random_ua}
        resp = http.post(
            URL,headers=header,
            json=req)
        data = resp.json()
        return data

    def get_data(self):
        """
        Run search_inpi function and return a dict database of the query
        """
        logging.info(f"----INPI SEARCHING----")
        json_data = self.search_inpi()
        data = json_data["result"]["hits"]["hits"]
        person_ = {}
        for i in range(len(data)):
            unity = data[i]["_source"]
            if "representants" in unity:
                person_[unity["denominationOuNomPatronymique"]] = unity
        return person_   

    def get_data_recap(self,enterprise):
        """
        Take the enterprise brut dict and return a cleaned dict in shape 
             "id" 
             "representants"
             "beneficiaires"
             "etablissements"
        """
        representatives = {}
        identity = {}
        benef = {}
        etablissements = {}

        ls = ['siren',"idt_pm_denomination",'idt_pm_activ_princip','idt_adr_siege_full','is_rad']
        identity= {k:v for k,v in enterprise.items() if k in ls}

        for i in range(len(enterprise["representants"])):
            person = enterprise["representants"][i]
            ls = ['nom_prenoms',"denomination",'type','qualites','date_naiss','nationalite','adr_rep_1','adr_rep_cp',"adr_rep_ville"]
            representatives[i] = {k:v for k,v in person.items() if k in ls} 

        try:
            for i in range(len(enterprise["beneficiaires"])):
                person = enterprise["beneficiaires"][i]
                ls = ['nom_naissance','prenoms','date_naissance','parts_totale']
                benef[i] = {k:v for k,v in person.items() if k in ls}
        except KeyError as k:
            logging.info(f"{k},is not in the data")
            pass

        try:            
            for i in range(len(enterprise["etablissements"])):
                etb = enterprise["etablissements"][i]
                ls = ['type','libelle_evt','libelle_activite','adr_ets_1','adr_ets_cp',"adr_ets_ville"]
                etablissements[i] = {k:v for k,v in etb.items() if k in ls}
        except KeyError as k:
            logging.info(f"{k},is not in the data")
            pass
                

        return  {"id":identity, 
                 "representants":representatives,
                 "beneficiaires": benef, 
                 "etablissements": etablissements}


    def get_filtred_data(self):
        """
        Filter data in order to take only enterprise where the query in present.
        """
        data = self.get_data()
        out = dict()
        for ent in data:
            rep = data[ent]["representants"]
            for i in range(len(rep)):
                if rep[i]["type"] == "P.Physique": 
                    nom_prenoms = self.normalize_(rep[i]["nom_prenoms"])       
                    normalized = self.normalize_(self.query)
                    if "date_naiss" in rep[i]:
                        bday = self.get_date_from_millisec(rep[i]["date_naiss"])
                        #!!je garde uniquemment les entreprises où la personne d'intéret fait partie des representants !! s'i l n'ya pas de dates de naissance je laisse pour eviters les bruits
                        if (self.jaccard_text_similarity(normalized,nom_prenoms) >=0.5) and (bday == self.mm_aaaa):
                            out[ent.upper()] = self.get_data_recap(data[ent])
#                             continue
#                     else:
#                         out[ent.upper()] = self.get_data_recap(data[ent])
        return out

        
    def getEntity(self,data):
        """
        Return evry enterprise of the data (dict keys)
        """
        return [_ for _ in self.data]

    def getPeople(self, data):
        """
        Get unique people and ensure they are different from query
        """
        people = []
        for ent in data:
            rep = data[ent]['representants']
            for p in rep:
                if rep[p]["type"] == "P.Physique":
                    nom_prenoms = self.normalize_(rep[p]["nom_prenoms"])
                    if 'date_naiss' in rep[p]:
                        date_ = rep[p]["date_naiss"]
                        if isinstance(date_,str):
                            people.append((nom_prenoms,date_))
                        else:
                            people.append((nom_prenoms,self.get_date_from_millisec(date_)))
                    else:
                        people.append(nom_prenoms)
                        
            benef = data[ent]["beneficiaires"]
            for ben in benef:
                nom_prenoms = self.normalize_(f'{benef[ben]["nom_naissance"]} {benef[ben]["prenoms"]}')
                if 'date_naissance' in benef[ben]:
                    date_ = benef[ben]["date_naissance"]
                    if isinstance(date_,str):
                        people.append((nom_prenoms,date_))
                    else:
                        people.append((nom_prenoms,self.get_date_from_millisec(date_)))
                else:
                    people.append(nom_prenoms)
                
        people = list(set(people))
        droplist = []
        compared = []
        for person in people:
            if len(person)>2:
                pass
            for i,j in enumerate(people):
                if (person == j) or ((i,j) in droplist) or ((person,j) in compared) or ((j,person) in compared):
                    pass
                elif self.jaccard_text_similarity(person[0],j[0]) >= 0.5 and (person[1]==j[1]):
                    compared.append((person,j)); compared.append((j,person))
                    droplist.append((i,j))
        people = [j for i,j in enumerate(people) if not i in [droplist[u][0] for u in range(len(droplist))]]
        
        return sorted(people,key=lambda x:x[0])

    
    def process_data(self):
        """
        Process the grabed data and return a cleaned one.
        Ex: Normalize names, transform date, correct query name if the jaccard similarity index is more than 0.5
        
        """
        
        data = self.get_filtred_data()
        people = self.getPeople(data)
        normalized = self.normalize_(self.query)
        logging.info(f"JIRAYA is PROCESSING {self.query}'s DATA")
        
        if len(data)==0:
            logging.info('THERE IS NO DATA')
            return {},{}
        else:
            for entity in data:
                #PROCESS REPS
                rep = data[entity]["representants"]
                for i in range(len(rep)):
                    if rep[i]["type"] == "P.Physique":
                        nom_prenoms = self.normalize_(rep[i]["nom_prenoms"])
                        rep[i]["nom_prenoms"] = nom_prenoms
                        if "date_naiss" in rep[i]:
                            date_ = rep[i]["date_naiss"]
                            if isinstance(date_,str):
                                pass
                            else:
                                rep[i]["date_naiss"]= self.get_date_from_millisec(date_)

                            if self.jaccard_text_similarity(normalized,nom_prenoms) >= 0.5 and (rep[i]["date_naiss"] == self.mm_aaaa) :
                                rep[i]["nom_prenoms"] = normalized
                                rep[i]["poi"] = 1
                            else:
    #                             rep[i]["nom_prenoms"] = nom_prenoms
                                rep[i]["poi"] = 0
                                for person in people:
                                    if len(person)==2 and (self.jaccard_text_similarity(person[0],nom_prenoms) >= 0.5) and (rep[i]["date_naiss"] == person[1]):
                                            rep[i]["nom_prenoms"] = person[0]

                    else:
                        if 'denomination' in rep[i]:
                            rep[i]["denomination"] = rep[i]["denomination"].upper()
                        else:
                            denom = [key for key in rep[i] if "denom" in key]
                            if len(denom)>0:
                                rep[i]["denomination"] = rep[i][denom[0]].upper()
                            else:
                                rep[i]["denomination"] = f"{rep[i].keys()}"


                #PROCESS BENEF
                benef = data[entity]["beneficiaires"]
                for ben in benef:
                    if all(x in benef[ben] for x in ['nom_naissance','prenoms']):
                        benef[ben]["nom_prenoms"] = self.normalize_(f'{benef[ben]["nom_naissance"]} {benef[ben]["prenoms"]}')
                        nom_prenoms = benef[ben]["nom_prenoms"]
                        if "date_naissance" in benef[ben]:
                            date_naiss = benef[ben]['date_naissance']
                            if isinstance(date_naiss,str):
                                pass
                            else:
                                benef[ben]['date_naissance']= self.get_date_from_millisec(date_naiss)

                            if self.jaccard_text_similarity(normalized,nom_prenoms) >= 0.5 and (benef[ben]["date_naissance"] == self.mm_aaaa) :
                                benef[ben]["nom_prenoms"] = normalized
                                benef[ben]["poi"] = 1
                            else:
    #                             benef[ben]["nom_prenoms"] = nom_prenoms
                                benef[ben]["poi"] = 0
                                for person in people:
                                    if len(person)==2 and (self.jaccard_text_similarity(person[0],nom_prenoms) >= 0.5) and (benef[ben]["date_naissance"] == person[1]):
                                        benef[ben]["nom_prenoms"] = person[0]                           

            return data , people
    
        
    def run(self): # __call__ 
        """
        Run the inpi class, return the data cleaned and save it . __call__ was not working but I don't remerber why .
        """
#         json_data = self.search_inpi()
        logging.info('HELLO STRANGER ^_^ \n KEEP CALM AND LET JIRAYA WORK')
        logging.info(f'JIRAYA is GATHERING {self.query} DATA')
        data , people = self.process_data()
        
        if len(data)==0:
            return {},{}
        else:
            path = f'./AllDatabase/{self.query}' #'./AllDatabase/jsonData'
            if not os.path.exists(path):
                os.makedirs(path)
            json.dump(data,open(f'{path}/{self.query}.json','w'))
            logging.info(f'DATA SAVED by JIRAYA AT {path}/{self.query}.json')
            return data , people

        
class Visualize(Inpi_person):
    """
    Class used to create Graph based on data grabed by Inpi_person's class
    """
    def __init__(self,query:str,mm_aaaa:str):
        super(Inpi_person)
        self.query = self.normalize_(query)
        self.mm_aaaa = mm_aaaa
        self.net = Network('650px',"950px", directed=True)         
        self.G = nx.DiGraph()
        self.data , self.people = Inpi_person(query,mm_aaaa).run()
        if len(self.data)>0:
            print('Number of entity:',len(self.data))
        else:
            logging.info('THERE IS NO DATA TO PLOT')
             
    def getEntity(self):
        """
        Return evry enterprise of the data (dict keys)
        """
        return [_ for _ in self.data]

    
    def getEntRecap(self,entity:dict):
        """
        Return a recap of each entity as a title of the node:
            "Nb représentants P.Physique"
            "Nb représentants P.Morale"
            "Nb bénéficiaires effectifs"
            "Nb établissements "
        """
        pp = 0
        pm = 0
        benef = len(entity["beneficiaires"])
        etb = len(entity["etablissements"])
        rep = entity["representants"]
        for p in rep:
            if rep[p]["type"] != "P.Physique":
                pm+=1
            else:
                pp+=1
        title= f'Siren:{entity["id"]["siren"]}'+"<br>"+ f'Nb représentants P.Physique:{pp}'+"<br>"+ f'Nb représentants P.Morale:{pm}'+"<br>"+ f'Nb bénéficiaires effectifs:{benef}'+"<br>"+ f'Nb établissements:{etb}'
        
        return title
                    
  
    def addNodes(self, G, data):
        """
        Go through the data te create nodes with attributes
        """
        logging.info('JIRAYA is CREATING NODES.')
        for entity in data: 
            entity_title = self.getEntRecap(data[entity])
            #create the entity's node
            G.add_node(entity, color ="green",weight=1, title = entity_title)
            rep = data[entity]["representants"]
            for i in rep:
                #create rep nodes and set their atributes base on the data colleted
                if rep[i]["type"] != "P.Physique":
                    name = rep[i]["denomination"]
                    G.add_node(name,color ="chocolate",weight=1)
                else:
                    name = rep[i]["nom_prenoms"]
                    t =['nationalite','date_naiss']
                    title = ' </br> '.join(f'{k}:{v}' for k,v in rep[i].items() if k in t)
                    
                    if rep[i]["poi"] == 1 :
                        G.add_node(name, color ="red",weight=len(data), title = title)
                    else:
                        if name in G.nodes():
                            #s'iel existait déjà, on ajoute le poids
                            G.nodes[name]["weight"]+=1
                        else:
                            self.G.add_node(name, color ="grey",weight=1, title = title)
                            
            
            benef = data[entity]["beneficiaires"]
            if len(benef) > 0:
                #create benef nodes and set their atributes base on the data colleted
                for b in benef:
                    name = benef[b]["nom_prenoms"]
                    if name in G.nodes():
                        #s'iel existait déjà, on ajoute le poids
                        G.nodes[name]["weight"]+=1
                    else:
                        #sinon on le crée
                        t =['parts_totale','date_naissance']
                        title = ' </br> '.join(f'{k}:{v}' for k,v in benef[b].items() if k in t)
                        G.add_node(name, color ="grey",weight=1, title = title)
                            
        return 1
                                
    def addEdges(self, G, data):
        """
        Go through the data te create edges with attributes
        """
        
        logging.info('JIRAYA is CREATING EDGES.')
        
        boss = ['Directeur général',
                 'Directeur général délégué',
                 'Directeur général,Administrateur',
                 'Gérant',
                 'Liquidateur',
                 'Président', "président",
                 "Président du conseil d'administration",
                 "Président du conseil d'administration,Directeur général",
                 'Président du directoire']
            
        for entity in data:
            #create edges and set their atributes base on the data colleted
            rep = data[entity]["representants"]
            for i in rep :
                if rep[i]["type"] != "P.Physique":
                    name = rep[i]["denomination"]
                    G.add_edge(name, entity, color = "orange")
                else:
                    name = rep[i]["nom_prenoms"]
                   
                    if rep[i]["qualites"][0] in boss :
                        G.add_edge(name,entity, color = 'red')
                    else:
                        G.add_edge(name,entity, color = 'orange')
            
            benef = data[entity]["beneficiaires"]
            for b in benef :
                name = benef[b]["nom_prenoms"]
                if G.nodes[name]["color"] == "red":
                    if (name,entity) in G.edges():
                        if G[name][entity]["color"]=='red':
                            G.add_edge(entity,name, color = 'red')
                        else:
                            G.add_edge(entity,name, color = 'purple')                                                   
                else:
                    G.add_edge(entity,name, color = 'purple')       
        return 1                            
                          
    
    def getNodes(self):
        """
        Return all the nodes created with their attribute
        """
        return self.G.nodes(data=True)
    
    
    def getEdges(self):
        """
        Return all the edges created
        """
        return self.G.edges()
    
    
    def resume_graph(self):
        """
        Get a resumed graph by selecting only people with degree>1 and all enterprise based on a subquery from the grpah's nodes
        """
        net = Network('800px',"1050px", directed=True)
        DegreeToKeep = [n for n in self.G.nodes() if (nx.degree(self.G)[n]>1) or (n.isupper())]
        H = self.G.subgraph(DegreeToKeep)
        net.from_nx(H)
        path = f'./AllDatabase/{self.query}'
        if not os.path.exists(path):
            os.makedirs(path)
        net.show(f'{path}/resume.html')
        
        
    def select_someone(self, nom_prenom):
        net = Network('800px',"1050px",notebook=True, directed=True)
        if not nom_prenom in self.G.nodes():
            print(nom_prenom,'not in the graph')
        else:
            related_1 = list(
                            set(
                                [n for n in nx.all_neighbors(self.G, nom_prenom)]
                                )
                            )
            nom_prenom_related = [nom_prenom] + list(
                                                    set(related_1 + list(set([n 
                                                                              for node in related_1 
                                                                              for n in nx.all_neighbors(self.G, node)]
                                                                            )
                                                                        )
                                                       )
                                                    )
            H = self.G.subgraph(nom_prenom_related)
            
            colors = [H[u][v]['color'] for u,v in H.edges()]
            nodecolors = [v['color'] for u,v in H.nodes(data=True)]
            
            plt.figure(figsize=(10, 10), dpi=90)
            nx.draw_random(H,node_color=nodecolors, edge_color=colors, 
                           with_labels=True,font_size=8, connectionstyle='arc3, rad = 0.1')
            net.from_nx(H)
            path = f'./AllDatabase/{self.query}/subgraph'
            if not os.path.exists(path):
                os.makedirs(path)
            net.show(f'{path}/{nom_prenom}.html')

    def inter_(self):
        return interact(lambda nodes:self.select_someone(nodes), nodes=[node for node in self.G.nodes()])
    
    def visualize(self, interact = False):
        self.addNodes(self.G,self.data)
        self.addEdges(self.G,self.data)
        self.net.from_nx(self.G), #self.net_exp.from_nx(self.G)                               
        path = f'./AllDatabase/{self.query}'
        
        if not os.path.exists(path):
            os.makedirs(path)
            
        self.net.show(f'{path}/full.html')

        json.dump(json_graph.node_link_data(self.G),open(f'{path}/graph.json','w'))
        self.resume_graph()
        if interact:
            self.inter_()
        logging.info(f'GRAPH SAVED by JIRAYA AT {path}')                                 
        return 1
        
                                        
    def get_Report(self):
        nb_ent = len(self.data)
        nb_people = len(self.people) - 1
        boss = [(k,v) for k,v in self.G.edges() if (self.G[k][v]['color']=="red") and (v==self.query or k==self.query)]
        boss = list(set([ent for edges in boss for ent in edges if ent.isupper()]))
        nb_boss = len(boss)

        cent = nx.degree_centrality(self.G)
        top_ten_central = sorted(cent, key=lambda x:cent[x] , reverse=True)[:10]
        top_ent_central = list(set([_ for _ in top_ten_central if _.isupper()]))
        top_people_central = list(set([_ for _ in top_ten_central if not _.isupper()]))

        communities_generator = nx.algorithms.community.girvan_newman(self.G)
        communities = next(communities_generator)
        communities =  sorted(map(sorted, communities), key =len, reverse=True)
        nb_communities = len(communities)

        path = f'./AllDatabase/{self.query}'
        if not os.path.exists(path):
            os.makedirs(path)

        with open(f'{path}/rapport_{self.query}.txt','w') as report:
            report.write("<meta charset='utf-8'/>")
            report.write('<div style="text-align:left"> </> \n')
            report.write(f'<h4> RAPPORT GRAPHE {self.query.upper()} </h4>')
            report.write(f'<p> Nombre d\'entités liées à {self.query}: {nb_ent} <br /> \n')
            report.write(f'Nombre de perosnnes liées à {self.query}: {nb_people} <br /> \n')
            report.write(f'Liste des entités dirigées par {self.query}: {boss}<br /> \n')
            report.write(f'Liste des entitées les plus influentes: {top_ent_central} <br /> \n')
            report.write(f'Liste des perosnnes les plus influentes: {top_people_central} <br /> \n')
            report.write(f'Nombre de communautés détectées: {nb_communities} </p>')
        
        logging.info(f'REPORT SAVED by JIRAYA AT {path}/rapport_{self.query}.txt')
        return 1
                            
    def visualize_and_report(self,interact = False):
        
        if len(self.data)>0:
            
            self.visualize(interact)
            self.get_Report()
            with open(f'./AllDatabase/{self.query}/rapport_{self.query}.txt','r') as report:
                text = report.readlines()
            with open(f'./AllDatabase/{self.query}/full.html','r') as htlm_viz:
                graph = htlm_viz.readlines()
            for i,line in enumerate(text):
                graph.insert(4+i,line)
            with open(f'./AllDatabase/{self.query}/full.html', "w") as f:
                graph = "".join(graph)
                f.write(graph)

            logging.info('See You Next Time, JIRAYA ^_^')
            
        return 1                               

    
class Plot_many(Visualize):
        
    def __init__(self, case_name:str, ls: list):
        assert isinstance(ls,list), ("ls n'est pas une liste")
        
        self.case_name = case_name
        self.ls = ls
        self.G = nx.DiGraph()
        self.net = Network('640px',"950px", directed=True)
    
    
    def jaccard_text_similarity(self,text_1:str, text_2:str):
        """
        This function take two text and return the jaccard similarity
        text_1 : input text 1
        text_2 : input text 2
        """
        t1 = text_1.split(" ")
        t2 = text_2.split(" ")
        text_1_inter_text_2 = len(list(set(t1) & set(t2)))
        return float(text_1_inter_text_2)/float(len(list(set(t1+t2))))
    
        
    def plot_(self):
        for elem in self.ls:
            viz = Visualize(elem[0],elem[1])
            viz.addNodes(self.G ,viz.data)
            viz.addEdges(self.G ,viz.data)
        
        mapping = {}
        for a,b in itertools.combinations(self.G.nodes,2):
            if self.jaccard_text_similarity(a,b) >=0.9:
                if self.G.nodes(data=True)[a]['color']=='red':
                    mapping[b]=a
                elif self.G.nodes(data=True)[b]['color']=='red':
                    mapping[a]=b
                else:
                    mapping[a]=b

        self.G = nx.relabel_nodes(self.G,mapping)
        
        path = f'./AllDatabase/{self.case_name}'
        if not os.path.exists(path):
            os.makedirs(path)
            
        self.net.from_nx(self.G)
        self.net.show(f'{path}/graph.html')
        json.dump(json_graph.node_link_data(self.G),open(f'{path}/graph.json','w'))
        logging.info(f'GRAPH SAVED by JIRAYA AT {path}')  
           

class check_Link(Visualize):
    def __init__(self,query, mm_aaaa,query2, mm_aaaa2,maxlevel=3):
        super(Inpi_person)
        self.query = self.normalize_(query)
        self.mm_aaaa = mm_aaaa
        self.query2 = self.normalize_(query2)
        self.mm_aaaa2 = mm_aaaa2
        self.maxlevel = maxlevel
        self.data, self.people = Inpi_person(query,mm_aaaa).process_data()
        self.check_link()
   
    def checkIf_Is_People(self,people1,people2):
        return (fuzz.ratio(people1[0],people2[0]) >= 50) and (people1[0] == people2[1])
    
    def checkIf_IsIn_People(self, people_ls:list):
        to_check = (self.query2,self.mm_aaaa2)
        poi = (self.query,self.mm_aaaa)
        for person in people_ls:
            if len(person)==2:
                if self.checkIf_Is_People(person,poi):
                    pass
                elif self.checkIf_Is_People(person,to_check):
                    return True
                else:
                    pass
                
    def check_link(self):
        logging.info('JIRAYA is CHECKING LEVEL 1')
        if self.checkIf_IsIn_People(self.people):
#             logging.info('JIRAYA founds link at level 1')
            print("JIRAYA founds a link at level 1")
            logging.info(f'JIRAYA inquires about {self.query2}')
            Visualize(self.query2,self.mm_aaaa2)

        else:
            logging.info('JIRAYA founds no link at level 1')
            level = 2
            actual_level_list = []
            while level<=self.maxlevel:
                if level == 2:
                    level_people_minus_ONE = self.people
                else:
                    level_people_minus_ONE = actual_level_list
                    actual_level_list = []
                logging.info(f'JIRAYA is CHECKING LEVEL {level}')
                no_link = []
                for p in level_people_minus_ONE:
                    if len(p)==2:
                        time.sleep(randint(2,4))
                        data, people = Inpi_person(p[0],p[1]).process_data()
                        actual_level_list.append(people)
                        actual_level_list = [p for ls in actual_level_list for p in ls]
                        if self.checkIf_IsIn_People(actual_level_list):
                            print("JIRAYA founds a link at level", level)
                            logging.info(f'JIRAYA inquires about {self.query2}')
                            Visualize(self.query2,self.mm_aaaa2)
                            break
                        else:
                            no_link.append(True)
                            continue
                
                if all(tuple(no_link)):
                    logging.info(f'JIRAYA founds no link at level {level}')
#                     print("JIRAYA founds no links at level", level)
                    level+=1

                                   
if __name__=='__main__':
    Visualize("Mignon Laurent","12/1963").visualize()

    