import sys
import json
import logging
import requests
import time
from datetime import datetime
from collections import defaultdict

from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache

from flask import Flask, render_template
from flask_frozen import Freezer

#global zKill instance for other pages
g_zKill = None

app = Flask(__name__)
freezer = Freezer(app)
app.config['FREEZER_DESTINATION'] = 'out/build'
app.config['FREEZER_RELATIVE_URLS'] = True

class zKillAPI():
    def __init__(self, do_file_cache, zkill_calls):
        self.do_file_cache = do_file_cache
        if self.do_file_cache:
            self.cached_sess = CacheControl(requests.Session(), cache_etags=False, cache=FileCache('.web_cache'))
            self.last_call_cache_hit = True
        self.zkill_calls = zkill_calls
        self.character_list = {}
        self.reverse_character_list = {}
        self.history = {}
        self.most_recent_killID = 0
        self.board_name = 'Polyhedra'

        with open('data/characters.json', 'r') as fd:
            self.character_list = json.load(fd)

        for name in self.character_list:
            self.reverse_character_list[str(self.character_list[name])] = name

        with open('data/pod_alliances.json', 'r') as fd:
            self.pod_alliances = json.load(fd)

        with open('data/target_alliances.json', 'r') as fd:
            self.target_alliances = json.load(fd)

        with open('data/target_banned_types.json', 'r') as fd:
            self.target_banned_types = json.load(fd)

        #load current history
        try:
            with open('out/data/history.json', 'r') as fd:
                self.history = json.load(fd)
        except FileNotFoundError:
            with open('out/data/history.json', 'a+') as faild:
                self.history = []
                json.dump(self.history, faild)

        #load ship_lookup (ID dictionary) json
        try:
            with open('out/data/ship_lookup.json', 'r') as fd:
                self.ship_lookup = json.load(fd)
        except FileNotFoundError:
            with open('out/data/ship_lookup.json', 'a+') as faild:
                json.dump({}, faild)
            self.ship_lookup = {}

        #load solarsystem_lookup (ID dictionary) json
        try:
            with open('out/data/solarsystem_lookup.json', 'r') as fd:
                self.solarsystem_lookup = json.load(fd)
        except FileNotFoundError:
            with open('out/data/solarsystem_lookup.json', 'a+') as faild:
                json.dump({}, faild)
            self.solarsystem_lookup = {}

        #load character_lookup (ID dictionary) json
        try:
            with open('out/data/character_lookup.json', 'r') as fd:
                self.character_lookup = json.load(fd)
        except FileNotFoundError:
            with open('out/data/character_lookup.json', 'a+') as faild:
                json.dump({}, faild)
            self.character_lookup = {}

        #load corp_lookup (ID dictionary) json
        try:
            with open('out/data/corp_lookup.json', 'r') as fd:
                self.corp_lookup = json.load(fd)
        except FileNotFoundError:
            with open('out/data/corp_lookup.json', 'a+') as faild:
                json.dump({}, faild)
            self.corp_lookup = {}

        #load alliance_lookup (ID dictionary) json
        try:
            with open('out/data/alliance_lookup.json', 'r') as fd:
                self.alliance_lookup = json.load(fd)
        except FileNotFoundError:
            with open('out/data/alliance_lookup.json', 'a+') as faild:
                json.dump({}, faild)
            self.alliance_lookup = {}

    def api_call_wrap(self, url):
        api_response = None
        if type(url) != str:
            raise ValueError('zKill:api_call_wrap was passed a url that was not a string')
        if self.do_file_cache:
            if self.last_call_cache_hit is False:
                time.sleep(1) # 'be polite' with requests (cached_sess)
            api_response = self.cached_sess.get(url)
            self.last_call_cache_hit = api_response.from_cache
        else:
            time.sleep(1)  # 'be polite' with requests
            api_response = requests.get(url)
            if api_response.ok == False:
                time.sleep(5) # assume timeout with one more try after a small wait
                api_response = requests.get(url)
                if api_response.ok == False:
                    #assume we have been locked out
                    raise ValueError(f'zKill:api_call_wrap api request was given garbage twice: \nurl: {url}\nresponse: {api_response.text}')
        return api_response

    def update_kill_history(self):
        api_call_frontstr = "http://zkillboard.com/api/characterID/"
        api_call_backstr = "/no-items/page/"
        raw_api_by_char = {}
        for name in self.character_list:
            api_call_minus_page_num = api_call_frontstr + str(self.character_list[name]) + api_call_backstr
            current_page = 1
            print('calling zkill: '+api_call_minus_page_num+str(current_page)+'/')
            raw_api_data = self.api_call_wrap(api_call_minus_page_num+str(current_page)+'/').json()
            raw_api_by_char[name] = raw_api_data
            while len(raw_api_data) != 0: #ensure there are no further pages
                current_page += 1
                print('calling zkill: ' +api_call_minus_page_num+str(current_page)+'/')
                raw_api_data = self.api_call_wrap(api_call_minus_page_num+str(current_page)+'/').json()
                raw_api_by_char[name] += raw_api_data
        #no more pages on the api with data
        for name in self.character_list: #for each character
            for kill in raw_api_by_char[name]: #for each kill
                if kill == []: #if we are at the end of the list ignore the last empty item
                    continue
                save_check = True
                for hist_kill in self.history: #if it exists already, don't append
                    if hist_kill['killmail_id'] == kill['killmail_id']:
                        save_check = False
                        break
                if save_check: #if it doesn't exist then append it
                    self.history.append(kill)

    def update_kill_details(self):
        api_call_frontstr = "https://esi.evetech.net/latest/killmails/"
        api_call_backstr = "/?datasource=tranquility&language=en-us"
        for kill in self.history:
            if kill.get('attackers') != None:
                continue
            if kill.get('ccp_esi', False):
                continue #no need to call ccp for this killmail
            api_call_id = str(kill['killmail_id'])
            api_call_hash = str(kill['zkb']['hash'])
            api_call = api_call_frontstr + api_call_id + '/' + api_call_hash + api_call_backstr
            print('calling ccp esi: '+api_call)
            raw_api_data = self.api_call_wrap(api_call).json()
            # grab all key
            for key in raw_api_data.keys():
                kill[key] = raw_api_data[key]
            kill['ccp_esi'] = True
        #set victim name

    def prune_unused_history_fields(self):
        for mail in self.history:
            mail.pop('moonID', None) #prune moon info
            mail.pop('position', None) #we don't need y,x,z in-space coords
            #mail['zkb'].pop('hash', None) #prune zkill hash value
            mail['zkb'].pop('points', None) #prune points metric because it means literally nothing
            mail['zkb'].pop('awox', None) #prune
            mail['victim'].pop('damage_taken', None) #prune
            mail['victim'].pop('items', None) #prune
            mail['victim'].pop('position', None) #prune
            if mail.get('involved', None) == None:
                mail['involved'] = len(mail['attackers']) # save number involved because we are pruning attackers
            pruned_attackers = []
            for attacker in mail['attackers']: #keep only those on character_list or final_blow == True
                if attacker.get('final_blow', None) or attacker.get('character_id', None) in self.character_list.values():
                    attacker.pop('securityStatus', None) # drop zkill sec status
                    attacker.pop('security_status', None) # drop esi sec status
                    attacker.pop('damage_done', None) # drop raw damage (not ehp)
                    attacker.pop('ship_type_id', None) # drop ship_type (it's mostly wrong on most mails)
                    attacker.pop('weapon_type_id', None) # drop weapon_type (it's mostly wrong on most mails)
                    pruned_attackers.append(attacker)
                    #save final_blow to top level location also
                    if attacker.get('final_blow', False):
                        mail['final_blow'] = attacker
            mail['attackers'] = pruned_attackers

    def tag_involved_characters(self):
        for mail in self.history:
            #if our_chracters tag exists, skip this mail
            if mail.get('our_characters', None) != None:
                continue
            #build an array of all of our characters involved
            involved = []
            for attacker in mail['attackers']:
                if attacker.get('character_id', None) in self.character_list.values():
                    temp_name = self.reverse_character_list[str(attacker['character_id'])]
                    involved.append(temp_name)
                    attacker['character_name'] = temp_name
                if attacker.get('character_id', None) != None and attacker.get('character_name', None) == None:
                    attacker['character_name'] = self.lookup_character_name(attacker['character_id'])
            mail['our_characters'] = involved
            mail['our_involved_html'] = ('<BR>'.join(x for x in involved))
            # tag alliance name, corp name, character_name
            if mail['victim'].get('alliance_id', None) != None:
                mail['victim']['alliance_name'] = self.lookup_alliance_name(mail['victim']['alliance_id'])
            if mail['victim'].get('corporation_id', None) != None:
                mail['victim']['corporation_name'] = self.lookup_corp_name(mail['victim']['corporation_id'])
            if mail['victim'].get('character_id', None) != None:
                mail['victim']['character_name'] = self.lookup_character_name(mail['victim']['character_id'])
            if mail['final_blow'].get('character_id', None) != None:
                mail['final_blow']['character_name'] = self.lookup_character_name(mail['final_blow']['character_id'])
            if mail['final_blow'].get('alliance_id', None) != None:
                mail['final_blow']['alliance_name'] = self.lookup_alliance_name(mail['final_blow']['alliance_id'])
            if mail['zkb'].get('npc', False): # NPC do not have character names
                if mail['final_blow'].get('character_id', None) == None:
                    mail['final_blow']['character_name'] = self.lookup_shipTypeID(mail['final_blow']['ship_type_id'])

    def tag_as_kill_loss_or_friendly_fire(self):
        for mail in self.history:
            #if row_type tag exists, skip this mail
            if mail.get('row_type', None) != None:
                continue
            #if one of our characters is the victim it is a loss
            if mail.get('victim', None) != None:
                if mail['victim'].get('character_id', None) in self.character_list.values():
                    #if one of our characters is on the killmail it's not just a loss
                    #it's a friendly fire incident
                    for attacker in mail['attackers']:
                        if attacker.get('character_id', None) in self.character_list.values():
                            mail['row_type'] = 'row-friendly_fire'
                            break
                    if mail.get('row_type', None) == None: # if it wasn't tagged friendly fire
                        mail['row_type'] = 'row-loss'      # then it's just a loss
                else: # if one of our characters isn't the victim then it is a kill
                    mail['row_type'] = 'row-kill'

    def lookup_alliance_name(self, theID):
        #if id present in self.alliance_lookup don't call the api
        temp_alliance_name = self.alliance_lookup.get(str(theID), None)
        if temp_alliance_name != None:
            return temp_alliance_name
        else: #better call ccp example: https://esi.evetech.net/latest/alliances/300578921/?datasource=tranquility&language=en-us
            api_call_front_str = 'https://esi.evetech.net/latest/alliances/'
            api_call = api_call_front_str + str(theID) + '/?datasource=tranquility&language=en-us'
            print('calling CCP: '+str(api_call))
            api_result = self.api_call_wrap(str(api_call)).json()
            theName = api_result['name']
            #and save result
            self.alliance_lookup[str(theID)] = theName
            return theName

    def lookup_corp_name(self, theID):
        #if id present in self.corp_lookup don't call the api
        temp_corp_name = self.corp_lookup.get(str(theID), None)
        if temp_corp_name != None:
            return temp_corp_name
        else: #better call ccp example: https://esi.evetech.net/latest/corporations/300578921/?datasource=tranquility&language=en-us
            api_call_front_str = 'https://esi.evetech.net/latest/corporations/'
            api_call = api_call_front_str + str(theID) + '/?datasource=tranquility&language=en-us'
            print('calling CCP: '+str(api_call))
            api_result = self.api_call_wrap(str(api_call)).json()
            theName = api_result['name']
            #and save result
            self.corp_lookup[str(theID)] = theName
            return theName

    def lookup_character_name(self, theID):
        #if id present in self.character_lookup don't call the api
        temp_character_name = self.character_lookup.get(str(theID), None)
        if temp_character_name != None:
            return temp_character_name
        else: #better call ccp example: https://esi.evetech.net/latest/characters/300578921/?datasource=tranquility&language=en-us
            api_call_front_str = 'https://esi.evetech.net/latest/characters/'
            api_call = api_call_front_str + str(theID) + '/?datasource=tranquility&language=en-us'
            print('calling CCP: '+str(api_call))
            api_result = self.api_call_wrap(str(api_call)).json()
            theName = api_result['name']
            #and save result
            self.character_lookup[str(theID)] = theName
            return theName

    def kill_counts(self, killtype):
        return len([x for x in self.history if x['row_type'] == killtype])

    def engineering_number_string(self, value):
        powers = [10 ** x for x in (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 100)]
        human_powers = ('k', 'm', 'b', 't', 'qa','qi', 'sx', 'sp', 'oct', 'non', 'dec', 'googol')
        try:
            value = int(value)
        except (TypeError, ValueError):
            return value

        if value < powers[0]:
            return str(value)
        for ordinal, power in enumerate(powers[1:], 1):
            if value < power:
                chopped = value / float(powers[ordinal - 1])
                format = ''
                if chopped < 10:
                    format = '%.2f'
                elif chopped < 100:
                    format = '%.1f'
                else:
                    format = '%i'
                return (''.join([format, human_powers[ordinal - 1]])) % chopped
        return str(value)

    def tag_formatted_values(self):
        for mail in self.history:
            #if count of minutes into day exists, skip. Used for sorting kills within a day
            if mail.get('minutes_into_day') == None:
                mail['minutes_into_day'] = int(mail['killmail_time'][11:13])*60+int(mail['killmail_time'][14:16])
            #if formatted_price tag exists, skip. Used for final web page output
            if mail.get('formatted_price') == None:
                mail['formatted_price'] = self.engineering_number_string(mail['zkb']['totalValue'])

    def kill_sums(self, killtype):
        r = sum(self.verify_kill(x, killtype) for x in self.history)
        return self.engineering_number_string(r)

    def verify_kill(self, k, killtype):
        if k['row_type'] in [killtype, 'row-friendly_fire']:
            if 'zkb' in k and 'totalValue' in k['zkb']:
                return k['zkb']['totalValue']
        return 0

    def format_date(self, dateval):
        year = str(int(dateval[0:4]))
        month = int(dateval[5:7])
        day = str(int(dateval[8:10]))
        monthname = ['','January', 'February', 'March', 'April', 'May', \
            'June', 'July', 'August', 'September', 'October', 'November', \
            'December']
        return monthname[month] + ' ' + day + ', ' + year

    def kills_by_date(self):
        kills = defaultdict(list)
        for kill in self.history:
            kills[kill['killmail_time'][0:10]].append(kill)
        kills_by_day = sorted(kills.items(), key=lambda x: x[0], reverse=True)
        result = []
        for day, killmails in kills_by_day:
            reversed_killmails = sorted(killmails, key=lambda x: x['minutes_into_day'], reverse=True)
            result.append((day, self.format_date(day), reversed_killmails))
        return result

    def pod_kills_by_date(self):
        kills = defaultdict(list)
        for kill in self.history:
            if kill['row_type'] != 'row-kill':
                continue
            if kill['victim'].get('alliance_id',0) not in self.pod_alliances:
                continue
            if kill['victim'].get('ship_type_id',0) != 670:
                continue
            if kill.get('final_blow',{}).get('character_name','') not in self.character_list.keys():
                continue
            kills[kill['killmail_time'][0:10]].append(kill)
        kills_by_day = sorted(kills.items(), key=lambda x: x[0], reverse=True)
        result = []
        for day, killmails in kills_by_day:
            reversed_killmails = sorted(killmails, key=lambda x: x['minutes_into_day'], reverse=True)
            result.append((day, self.format_date(day), reversed_killmails))
        return result

    def target_kills_by_date(self):
        kills = defaultdict(list)
        for kill in self.history:
            if kill['row_type'] != 'row-kill':
                continue
            if kill['victim'].get('alliance_id',0) not in self.target_alliances:
                continue
            if kill['victim'].get('ship_type_id',0) in self.target_banned_types:
                continue
            #uncomment if being used for final blow only tracking
            #if kill.get('final_blow',{}).get('character_name','') not in self.character_list.keys():
            #    continue
            kills[kill['killmail_time'][0:10]].append(kill)
        kills_by_day = sorted(kills.items(), key=lambda x: x[0], reverse=True)
        result = []
        for day, killmails in kills_by_day:
            reversed_killmails = sorted(killmails, key=lambda x: x['minutes_into_day'], reverse=True)
            result.append((day, self.format_date(day), reversed_killmails))
        return result

    def tag_solarSystemName(self):
        for mail in self.history:
            theID = mail['solar_system_id']
            if mail.get('solar_system_name', None) != None:
                continue
            #if solarSystemID present in self.solarsystem_lookup don't call the api
            temp_solarsystem_name = self.solarsystem_lookup.get(str(theID), None)
            if temp_solarsystem_name != None:
                mail['solar_system_name'] = temp_solarsystem_name
            else: #better call CCP example: https://esi.evetech.net/latest/universe/systems/30002022/?datasource=tranquility&language=en-us
                api_call_front_str = 'https://esi.evetech.net/latest/universe/systems/'
                api_call = api_call_front_str+str(theID)+'/?datasource=tranquility&language=en-us'
                print('calling CCP: '+str(api_call))
                api_result = self.api_call_wrap(str(api_call)).json()
                theName = api_result['name']
                mail['solar_system_name'] = theName
                #and save this result so we don't call CCP again
                self.solarsystem_lookup[str(theID)] = theName

    def tag_shipTypeID(self):
        for mail in self.history:
            theID = mail['victim']['ship_type_id']
            if mail['victim'].get('ship_type_name', None) != None:
                continue
            mail['victim']['ship_type_name'] = self.lookup_shipTypeID(theID)

    def lookup_shipTypeID(self, theID):
        temp_ship_name = self.ship_lookup.get(str(theID), None)
        if temp_ship_name != None:
            return temp_ship_name
        else: #better call CCP example: https://esi.evetech.net/latest/universe/types/603/?datasource=tranquility&language=en-us
            api_call_front_str = 'https://esi.evetech.net/latest/universe/types/'
            api_call = api_call_front_str + str(theID) + '/?datasource=tranquility&language=en-us'
            print('calling CCP: '+ api_call)
            api_result = self.api_call_wrap(str(api_call)).json()
            theName = api_result['name']
            #and save this result so we don't call CCP again
            self.ship_lookup[str(theID)] = theName
            return theName

    def use_character(self, charid):
        cs = {v:k for k,v in self.character_list.items()}
        charname = cs[charid]
        self.history = [x for x in self.history if charname in x['our_characters'] or charname == x['victim']['character_name']]
        self.board_name = charname

    def write_data_to_file(self):
        print('writing data')
        with open('out/data/history.json', 'w') as outfile:
            json.dump(self.history, outfile)
        with open('out/data/ship_lookup.json', 'w') as outfile:
            json.dump(self.ship_lookup, outfile)
        with open('out/data/solarsystem_lookup.json', 'w') as outfile:
            json.dump(self.solarsystem_lookup, outfile)
        with open('out/data/character_lookup.json', 'w') as outfile:
            json.dump(self.character_lookup, outfile)
        with open('out/data/corp_lookup.json', 'w') as outfile:
            json.dump(self.corp_lookup, outfile)
        with open('out/data/alliance_lookup.json', 'w') as outfile:
            json.dump(self.alliance_lookup, outfile)

    def update_all(self):
        if self.zkill_calls:
            self.update_kill_history()
        self.update_kill_details()
        self.prune_unused_history_fields()
        self.tag_involved_characters()
        self.tag_as_kill_loss_or_friendly_fire()
        self.tag_formatted_values()
        self.tag_solarSystemName()
        self.tag_shipTypeID()
        self.write_data_to_file()

    @property
    def data(self):
        characters = len(self.character_list)
        result = {'kills':           self.kill_counts('row-kill'),
                  'losses':          self.kill_counts('row-loss'),
                  'history':         self.kills_by_date(),
                  'characters':      sorted(self.character_list.items()),
                  'money_lost':      self.kill_sums('row-loss'),
                  'money_killed':    self.kill_sums('row-kill'),
                  'friendly_fire':   self.kill_counts('row-friendly_fire'),
                  'character_count': characters,
                  'board_name':      self.board_name}
        return result

    @property
    def pods(self):
        characters = len(self.character_list)
        result = {'kills':           self.kill_counts('row-kill'),
                  'losses':          self.kill_counts('row-loss'),
                  'history':         self.pod_kills_by_date(),
                  'characters':      sorted(self.character_list.items()),
                  'money_lost':      self.kill_sums('row-loss'),
                  'money_killed':    self.kill_sums('row-kill'),
                  'friendly_fire':   self.kill_counts('row-friendly_fire'),
                  'character_count': characters,
                  'board_name':      self.board_name+" Target Pods"}
        return result

    @property
    def targets(self):
        characters = len(self.character_list)
        result = {'kills':           self.kill_counts('row-kill'),
                  'losses':          self.kill_counts('row-loss'),
                  'history':         self.target_kills_by_date(),
                  'characters':      sorted(self.character_list.items()),
                  'money_lost':      self.kill_sums('row-loss'),
                  'money_killed':    self.kill_sums('row-kill'),
                  'friendly_fire':   self.kill_counts('row-friendly_fire'),
                  'character_count': characters,
                  'board_name':      self.board_name+" Targets"}
        return result

@freezer.register_generator
def index():
    #build main board
    yield '/'
    # build podkills list
    #yield '/target_pods/' # no longer needed
    # build ships list
    yield '/target_ships/'

@app.route('/')
def index():
    print('index')
    return render_template('index.html', **g_zKill.data)

#@app.route('/target_pods/')
#def target_pods():
#    print('pods')
#    return render_template('index.html', **g_zKill.pods)

@app.route('/target_ships/')
def target_ships():
    print('targets')
    return render_template('index.html', **g_zKill.targets)

if __name__ == "__main__":
    if (len(sys.argv) > 1 and sys.argv[1] == 'debug') or (len(sys.argv) > 2 and sys.argv[2] == 'debug') or (len(sys.argv) > 3 and sys.argv[3] == 'debug'):
        logging.basicConfig(level=logging.DEBUG)
    if (len(sys.argv) > 1 and sys.argv[1] == 'no_file_cache') or (len(sys.argv) > 2 and sys.argv[2] == 'no_file_cache') or (len(sys.argv) > 3 and sys.argv[3] == 'no_file_cache'):
        do_file_cache = False
    else:
        do_file_cache = True
    if (len(sys.argv) > 1 and sys.argv[1] == 'no_zkill_calls') or (len(sys.argv) > 2 and sys.argv[2] == 'no_zkill_calls') or (len(sys.argv) > 3 and sys.argv[3] == 'no_zkill_calls'):
        zkill_calls = False
    else:
        zkill_calls = True
    print('main build')
    zKill = zKillAPI(do_file_cache, zkill_calls)
    zKill.update_all()
    print('update success')
    print('latest ID: '+str(zKill.kills_by_date()[0][2][0]['killmail_id']))
    g_zKill = zKill
    freezer.freeze()

    #app.run(debug=True, host='0.0.0.0')
