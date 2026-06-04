from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

def index(request):
    return render(request, 'cartaNatura/index.html')    

@csrf_exempt
def gis(request):
    if request.method == 'POST':
        import json
        import pandas as pd
        import geopandas
        import os
        senzaNatura = ['Acerra', 'Afragola', 'Arzano', 'Aversa', 'Bellizzi', 'Boscoreale', 'Brusciano', 'Caivano', 'Calvizzano', 'Camposano', 'Capodrise', 'Cardito', 'Carinaro', 'Casagiove', 'Casal di Principe', 'Casalnuovo di Napoli', 'Casaluce', 'Casandrino', 'Casapesenna', 'Casapulla', 'Casavatore', 'Casoria', 'Castello di Cisterna', 'Cercola', 'Cesa', 'Cicciano', 'Cimitile', 'Comiziano', 'Crispano', 'Curti', 'Frattamaggiore', 'Frattaminore', 'Frignano', 'Gricignano di Aversa', 'Grumo Nevano', 'Liveri', 'Lusciano', 'Macerata Campania', 'Marcianise', 'Mariglianella', 'Marigliano', 'Marzano di Nola', 'Melito di Napoli', 'Mugnano di Napoli', 'Nola', 'Orta di Atella', 'Pastorano', 'Poggiomarino', "Pomigliano d'Arco", 'Pompei', 'Portico di Caserta', 'Qualiano', 'Recale', "San Cipriano d'Aversa", 'San Gennaro Vesuviano', 'San Giorgio a Cremano', 'San Marcellino', 'San Marco Evangelista', 'San Marzano sul Sarno', 'San Nicola la Strada', 'San Paolo Bel Sito', 'San Tammaro', 'San Valentino Torio', 'San Vitaliano', "Sant'Antimo", "Sant'Arpino", 'Santa Maria Capua Vetere', 'Santa Maria la Carita', 'Saviano', 'Scafati', 'Scisciano', 'Sparanise', 'Striano', 'Succivo', 'Teverola', 'Torre Annunziata', 'Trentola-Ducenta', 'Tufino', 'Villa Literno', 'Villa di Briano', 'Volla']
        json_data = json.loads(request.body.decode('utf-8'))
        string_data = str(json_data)
        string_data = string_data.replace("'", '"')
        string_data = string_data.replace('"COM_MON": None','"COM_MON":null')
        ########
        string_data = string_data.replace('Barano d"Ischia',"Barano d'Ischia")
        string_data = string_data.replace('Cava de" Tirreni',"Cava de' Tirreni")
        string_data = string_data.replace('Fragneto l"Abate',"Fragneto l'Abate")
        string_data = string_data.replace('Ospedaletto d"Alpinolo',"Ospedaletto d'Alpinolo")
        string_data = string_data.replace('Pomigliano d"Arco',"Pomigliano d'Arco")
        string_data = string_data.replace('Rocca d"Evandro',"Rocca d'Evandro")
        string_data = string_data.replace('San Cipriano d"Aversa',"San Cipriano d'Aversa")
        string_data = string_data.replace('Sant"Agata de" Goti',"Sant'Agata de' Goti")
        string_data = string_data.replace('Sant"Agnello',"Sant'Agnello")
        string_data = string_data.replace('Sant"Anastasia',"Sant'Anastasia")
        string_data = string_data.replace('Sant"Andrea di Conza',"Sant'Andrea di Conza")
        string_data = string_data.replace('Sant"Angelo a Cupolo',"Sant'Angelo a Cupolo")
        string_data = string_data.replace('Sant"Angelo a Fasanella',"Sant'Angelo a Fasanella")
        string_data = string_data.replace('Sant"Angelo a Scala',"Sant'Angelo a Scala")
        string_data = string_data.replace('Sant"Angelo all"Esca',"Sant'Angelo all'Esca")
        string_data = string_data.replace('Sant"Angelo d"Alife',"Sant'Angelo d'Alife")
        string_data = string_data.replace('Sant"Angelo dei Lombardi',"Sant'Angelo dei Lombardi")
        string_data = string_data.replace('Sant"Antimo',"Sant'Antimo")
        string_data = string_data.replace('Sant"Antonio Abate',"Sant'Antonio Abate")
        string_data = string_data.replace('Sant"Arcangelo Trimonte',"Sant'Arcangelo Trimonte")
        string_data = string_data.replace('Sant"Arpino',"Sant'Arpino")
        string_data = string_data.replace('Sant"Arsenio',"Sant'Arsenio")
        string_data = string_data.replace('Sant"Egidio del Monte Albino',"Sant'Egidio del Monte Albino")
        string_data = string_data.replace('Valle dell"Angelo',"Valle dell'Angelo")
        ########
        path_shape = os.path.join(os.path.dirname(__file__), 'shapeCN', 'CNPulita.shp')
        shapes = geopandas.read_file(path_shape)
        shapes = shapes.to_crs(epsg=4326)
        print(string_data)
        geometrie = json.loads(string_data)
        #CASO IN CUI HO SIA POLIGONI CHE COMUNI 
        if(len(geometrie['aree']) == 2) :
            geojson1 = geopandas.GeoDataFrame.from_features(geometrie['aree'][0]['features'])
            geojson1 = geojson1.set_crs(epsg=32633)
            geojson1 = geojson1.to_crs(epsg=4326)
            result1 = geopandas.clip(shapes, geojson1, keep_geom_type=False)
            geojson2 = geopandas.GeoDataFrame.from_features(geometrie['aree'][1]['features'])
            geojson2 = geojson2.set_crs(epsg=4326, inplace=True)
            result2 = geopandas.clip(shapes, geojson2, keep_geom_type=False)
            finalresult = pd.concat([result1,result2])
            ############################  RECUPERO I COMUNI INTERSECATI DAI POLIGONI  ################################
            path_campania = os.path.join(os.path.dirname(__file__), 'static', 'util' ,'moddedCampania.geojson')
            f2 = open(path_campania , 'r')
            campania = json.loads(f2.read())
            f2.close()
            campaniageojson = geopandas.GeoDataFrame.from_features(campania['features'])
            campaniageojson.set_crs(epsg=4326, inplace=True)
            result2.set_crs(epsg=4326, inplace=True)
            result = geopandas.clip(campaniageojson, result2, keep_geom_type=False)
            listaComuni = list(set(result['COMUNE'].unique().tolist() + geojson1['COMUNE'].unique().tolist()))
            jsonDaRestituire = json.loads('{"ris" : []}')
            jsonRisultato = json.loads(finalresult.to_json())
            jsonDaRestituire['ris'].append(jsonRisultato)
            jsonDaRestituire['ris'].append([x for x in listaComuni if x not in senzaNatura])
            return HttpResponse(json.dumps(jsonDaRestituire), content_type='application/json')
        #CASO IN CUI HO SOLO COMUNI
        elif (geometrie['aree'][0]['features'][0]['geometry']['type'] == 'MultiPolygon'):
            geojson1 = geopandas.GeoDataFrame.from_features(geometrie['aree'][0]['features'])
            geojson1 = geojson1.set_crs(epsg=32633)
            geojson1 = geojson1.to_crs(epsg=4326)
            result1 = geopandas.clip(shapes, geojson1, keep_geom_type=False)
            listaComuni = geojson1['COMUNE'].unique().tolist()
            jsonDaRestituire = json.loads('{"ris" : []}')
            jsonRisultato = json.loads(result1.to_json())
            jsonDaRestituire['ris'].append(jsonRisultato)
            jsonDaRestituire['ris'].append([x for x in listaComuni if x not in senzaNatura])
            return HttpResponse(json.dumps(jsonDaRestituire), content_type='application/json')
            
        #CASO IN CUI HO SOLO POLIGONI
        else:
            geojson2 = geopandas.GeoDataFrame.from_features(geometrie['aree'][0]['features'])
            geojson2 = geojson2.set_crs(epsg=4326, inplace=True)
            result2 = geopandas.clip(shapes, geojson2, keep_geom_type=False)
            ############################  RECUPERO I COMUNI INTERSECATI DAI POLIGONI  ################################
            path_campania = os.path.join(os.path.dirname(__file__), 'static', 'util' ,'moddedCampania.geojson')
            f2 = open(path_campania , 'r')
            campania = json.loads(f2.read())
            f2.close()
            campaniageojson = geopandas.GeoDataFrame.from_features(campania['features'])
            campaniageojson.set_crs(epsg=4326, inplace=True)
            result2.set_crs(epsg=4326, inplace=True)
            result = geopandas.clip(campaniageojson, result2, keep_geom_type=False)
            listaComuni = result['COMUNE'].unique().tolist()
            jsonDaRestituire = json.loads('{"ris" : []}')
            jsonRisultato = json.loads(result2.to_json())
            jsonDaRestituire['ris'].append(jsonRisultato)
            jsonDaRestituire['ris'].append([x for x in listaComuni if x not in senzaNatura])
            return HttpResponse(json.dumps(jsonDaRestituire), content_type='application/json')
    else:
        return HttpResponse('Richiesta non valida')
        


##def comuniInteressati(request):
##    if request.method == 'POST':
##        import json
##        import pandas as pd
##        import geopandas
##        import os
##        json_data = json.loads(request.body.decode('utf-8'))
##        string_data = str(json_data)
##        string_data = string_data.replace("'", '"')
##        geometrie = json.loads(string_data)
##        path_campania = os.path.join(os.path.dirname(__file__), 'static', 'util' ,'moddedCampania.geojson')
##        f2 = open(path_campania , 'r')
##        campania = json.loads(f2.read())
##        f2.close()
##        geometriegeojson = geopandas.GeoDataFrame.from_features(geometrie['features'])
##        campaniageojson = geopandas.GeoDataFrame.from_features(campania['features'])
##        geometriegeojson.set_crs(epsg=4326)
##        campaniageojson.set_crs(epsg=4326)
##        result = geopandas.clip(campaniageojson, geometriegeojson, keep_geom_type=False)
##        comuni = result['COMUNE'].unique().tolist()
##        print(comuni)
##        return HttpResponse(json.dumps({'comuni':comuni}), content_type='application/json')
##    else:
##        return HttpResponse('Richiesta naaaaon valida')
                