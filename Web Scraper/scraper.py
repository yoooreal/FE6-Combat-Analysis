# Scrape data off of fireemblemwiki.org. This script works at the time of writing, 8/11/25.

import requests
from bs4 import BeautifulSoup
from pprint import pprint
import re
import csv

ULIST = 'https://fireemblemwiki.org/wiki/List_of_characters_in_Fire_Emblem:_The_Binding_Blade'
MLIST = 'https://fireemblemwiki.org/wiki/List_of_chapters_in_Fire_Emblem:_The_Binding_Blade'
WLIST = 'https://fireemblemwiki.org/wiki/List_of_weapons_in_Fire_Emblem:_The_Binding_Blade'

def fetch(url):
  return  BeautifulSoup(requests.get(url).content, 'html.parser')

def findBetween(**kwargs):
  for e in kwargs['start'].findNextSiblings():
    if e == kwargs['end']:
      break
    elif kwargs['test'](e):
      return e
  return False

#### ------- Player Unit Data ------- ##
def scrapeUnitLinks():
  print('Gathering wiki links... ', end='')
  page = fetch(ULIST)
  links = []

  playableUnits = page.find('span', text='Main story', class_='mw-headline')  \
                      .findNext('tbody')  \
                      .findChildren('tr')
  
  for row in playableUnits:
    cells = row.findChildren('a')
    
    if len(cells) > 1 and cells[1]:
      links.append('https://fireemblemwiki.org' + cells[1]['href'])
  
  print('Done.')
  return links

def weaponName(a): # For use on image links.
  return a['title'].lower().replace(' magic', '')

def listToStats(arr):
  t = { 'hp': arr[0], 'luk': arr[1], 'pow': arr[2], 'def': arr[3],
        'skl': arr[4], 'res': arr[5], 'spe': arr[6] }
        
  if len(arr) > 7:
    t['con'], t['move'] = arr[7], arr[8]

  return t

def scrapeUnitDatum(url): # Get the data for a single unit.
  page = fetch(url)
  data = {
    'name': '',
    'promotedClass': False,
    'promotionBonus': False,
    # Some data will vary based on join circumstances.
    'join': {
      'Normal, Ch. 10A': {
        'startingClass': '',
        'startingLevel': 0,
        'bases': {'hp': '0', 'pow': '0'}, # etc.
        'growths': { 'hp': 0.0, 'pow': 0.0, 'skl': 0.0 }, # etc.
        'wranks': { 'swords': False, 'anima': False, 'staves': False }, # etc.
        'inventory': []
      },
      'Hard, Ch. 10B': False
    }
  }
  
  data['name'] = page.find('span', class_ = 'mw-page-title-main').text  \
                                                                 .replace('(character)', '')  \
                                                                 .strip()
  print('Scraping ' + data['name'] + '\'s data... ', end='')
  
  # Most of what we want will be under the Binding Blade header.
  FE6 = page.find('span', id='Fire_Emblem:_The_Binding_Blade').findParent()
  analysis = FE6.findNext('span', id='Analysis').findParent()
  
  # Check if unit stats vary based on join circumstances.
  multipleJoins = findBetween(start = FE6, end = analysis,
    test = lambda e: e.name == 'div' and e.findChild('div', class_='tabcontainer'))
  outerTable = None
  
  if multipleJoins:
    tabList = multipleJoins.find('p').findChildren('span', recursive=False)
    tabs = [tab.text.strip() for tab in tabList]
    outerTable = FE6.findNext('div', class_='tabcontents')  \
                    .findChildren('div', class_='tab_content', recursive=False)
  else:
    tabs = ['Normal']
    outerTable = [FE6.findNext('tbody')]
  
  data['join'] = {}
  for i in range(len(tabs)):
    tab = tabs[i]
    columns = outerTable[i].findNext('tr').findChildren('td', recursive=False)
    left, right = columns[0], columns[1]
    
    joinData = {
      'startingClass': left.findNext('i').text,
      'startingLevel': left.findChildren('tr')[2].find('td').text.strip()
    }
    
    tables = right.findNext('tbody').findChildren('tbody')
    
    joinData['bases'] = listToStats([n.text.strip() for n in tables[0].findChildren('td')])
    joinData['growths'] = listToStats([n.text.strip() for n in tables[1].findChildren('td')])
    
    inventory = tables[2].findChildren('tr')[1].findChildren('span')
    joinData['inventory'] = [item.text.strip(' *') for item in inventory
                               if item.text.strip(' *') and item.text.strip(' *') != '--']
    
    wranks = tables[2].findChildren('tr')[2].findChildren('td')[0]  \
                                            .findNext('tbody').findChildren('td')
    accum = {}
    for i in range(0, len(wranks), 2):
      weapon = weaponName(wranks[i].find('a'))
      rank = wranks[i+1].text.strip()
    
      # We want weapon rank as a number value so it's easier to calc changes later.
      numeric = False
      if rank == 'E': numeric = 1
      elif rank == 'D': numeric = 51
      elif rank == 'C': numeric = 101
      elif rank == 'B': numeric = 151
      elif rank == 'A': numeric = 201
      elif rank == 'S': numeric = 251
      
      accum[weapon] = numeric
    
    joinData['wranks'] = accum
    data['join'][tab] = joinData
  
  # Lastly, we need to check for promotion bonuses, since they vary from unit to unit.
  promotion = findBetween(start = FE6, end = analysis,
    test = lambda e: e.name == 'h3' and e.find('span', id='Promotion_stat_gains'))
  
  if promotion:
    promoTable = promotion.findNext('tbody').findChildren('tr')[1]
    bonuses = [item.text.strip() for item in promoTable if item.text.strip()]
    data['promotedClass'] = bonuses[0]
    
    nBonus = [int(numeric) for numeric in bonuses[1:10]]
    data['promotionBonus'] = { 'hp': nBonus[0], 'pow': nBonus[1], 'skl': nBonus[2],
      'spe': nBonus[3], 'luk': nBonus[4], 'def': nBonus[5], 'res': nBonus[6],
      'con': nBonus[7], 'move': nBonus[8]
    }
    
    promoRanks = promoTable.find('td', class_='roundbr')
    weapons = [weaponName(weapon) for weapon in promoRanks.findChildren('a')]
    
    # The text formatting for promotion WEXP is weird and inconsistent across pages.
    pass1 = [x.replace('WEXP', '').replace('(+1)', '').replace('D (+', '')
              .strip('ABCDS+,( )')
              for x in bonuses[10].split(' +') if x]
    ranks = []
    for x in pass1:
      for strFragment in re.split(' |,', x):
        if strFragment:
          if strFragment == 'E':
            ranks.append(1)
          else:
            ranks.append(int(strFragment))
    
    for i in range(len(weapons)):
      data['promotionBonus'][weapons[i]] = ranks[i]
  
  print('Done.')
  return data

def scrapeUnitData():
  print('Scraping player unit data...')
  data = [scrapeUnitDatum(url) for url in scrapeUnitLinks()]
  print('Done.')
  return data

#### ------- Enemy Data ------- ##
def scrapeMapLinks():
  print('Gathering wiki links... ', end='')
  
  page = fetch(MLIST)
  links = []
  
  chapters = page.find('span', id='Main_story').findNext('tbody').findChildren('tr')[2:]
  for chapter in chapters:
    # We can find useful information aside from just page links here.
    info = chapter.findChildren('td')
    chapterNumber = info[0].text.strip().replace(u'\xa0', ' ')
    link = 'https://fireemblemwiki.org' + info[1].find('a')['href']
    newUnits = [name.text for name in info[4].findChildren('a')]
    bosses = [bossName.text for bossName in info[5].findChildren('a')]
    
    links.append({'number': chapterNumber, 'url': link, 'newUnits': newUnits,
                  'bosses': bosses})

  print('Done.')
  
  return links

def extractEnemyData(table, data, difficulty, reinforcements):
  cells = table.findChildren('td', recursive=False)
  enemy = {
    'difficulty': difficulty,
    'reinforcement': reinforcements,
    'name': cells[1].text.strip() or cells[1].findChild().text.strip(),
    'class': cells[2].findChild().text.strip(),
    'level': cells[3].text.strip(),
    'quantity': cells[4].text.strip(),
    'hp': cells[5].text.strip(),
    'pow': cells[6].text.strip(),
    'skl': cells[7].text.strip(),
    'spe': cells[8].text.strip(),
    'luk': cells[9].text.strip(),
    'def': cells[10].text.strip(),
    'res': cells[11].text.strip(),
    'con': cells[12].text.strip(),
    'move': cells[13].text.strip(),
    'inventory': [ item.findChild('span').text.strip() for item in  \
                    cells[14].findChildren('a') if item.findChild('span') ]
  }
  enemy['boss'] = any(name in [enemy['name']] for name in data['bosses'])
  enemy['recruitable'] = any(name in [enemy['name']] for name in data['newUnits'])
  
  return enemy

def scrapeMapDatum(map): # Get the enemy data for a single map.
  print('Scraping ' + map['number'] + ' data...', end='')

  page = fetch(map['url'])
  data = { 'number': map['number'], 'newUnits': map['newUnits'], 'bosses': map['bosses'],
    'enemies': []
  }
  
  enemyHeader = page.find('span', id='Enemy_data').findParent()
  bossHeader = page.find('span', id='Boss_data').findParent()
  
  enemyTable = findBetween(start = enemyHeader, end = bossHeader,
    test = lambda e: e if e.name == 'div' and e.findChild('div', class_='tabcontainer')  \
                       else False)
                       
  difficultyTabs = enemyTable.findChild('div', class_='tabcontainer').findChildren('span')
  enemyTables = enemyTable.findChild('div', class_='tabcontents')  \
                     .findChildren('div', class_='tab_content')
  
  enemies = []
  for i in range(len(difficultyTabs)):
    difficulty = difficultyTabs[i].text.strip()
    tables = enemyTables[i].find('tbody').findChildren('tr', recursive=False)
    
    # Scrape enemies that start on the map.
    startingEnemies = tables[1].findChildren('tr')
    for j in range(len(startingEnemies)):
      if j % 2 == 1:
        enemies.append(extractEnemyData(startingEnemies[j], data, difficulty, False))
    
    # Scrape reinforcements, if there are any.
    reinforcements = False
    if len(tables) >= 4:
      reinforcements = tables[3].findChildren('tr')
      for k in range(len(reinforcements)):
        if k % 2 == 1:
          enemies.append(extractEnemyData(reinforcements[k], data, difficulty, True))
    
    data['enemies'] = enemies
  
  print('Done.')
  
  return data

def scrapeMapData():
  print('Scraping map data...')
  
  data = [scrapeMapDatum(map) for map in scrapeMapLinks()]
  
  print('Done.')
  
  return data

#### ------- Enemy Data ------- ##
def scrapeWeaponData():
  print('Scraping weapon data... ', end='')
  
  page = fetch(WLIST)
  data = []
  
  header = page.find('h1', id='firstHeading')
  table = header.findNext('tbody')
  
  
  for row in table.findChildren('tr')[1:]:
    cells = row.findChildren('td')
    data.append({
      'weapon': cells[0].findChild().text.strip(),
      'type': cells[2].findChildren('a')[0].text.strip() or  \
              cells[2].findChildren('a')[1].text.strip(),
      'level': cells[3].text.strip(),
      'might': cells[4].text.strip(),
      'weight': cells[5].text.strip(),
      'hit': cells[6].text.strip(),
      'crit': cells[7].text.strip(),
      'range': cells[8].text.strip().replace(u'\xa0', ' '),
      'uses': cells[9].text.strip(),
      'price': cells[10].text.strip(),
      'notes': cells[11].text.strip().replace(u'\xa0', ' ') or  \
               cells[11].findChild().text.strip().replace(u'\xa0', ' ')
    })
  
  print('Done.')
  
  return data


#### ------- Export to CSV ------- ##
unitsPy = scrapeUnitData()
mapsPy = scrapeMapData()
weaponsPy = scrapeWeaponData()

# We need to convert our python objects to nested arrays first.
def si(index, arr): # Safe Index
  if index < len(arr):
    return arr[index]
  else:
    return False
    
def sh(key, table): # Safe Hash
  if key in table.keys():
    return table[key]
  else:
    return False

unitsCsv = [['Name', 'joinDifficulty',
             'HP', 'Power', 'Skill', 'Speed', 'Luck', 'Defense', 'Resistance',
             'Constitution', 'Move',
             'HP Growth', 'Power Growth', 'Skill Growth', 'Speed Growth', 'Luck Growth',
             'Defense Growth', 'Resistance Growth',
             'Class', 'Level',
             'Item 1', 'Item 2', 'Item 3', 'Item 4', 'Item 5',
             'Sword Rank', 'Lance Rank', 'Axe Rank', 'Bow Rank', 'Anima Rank', 'Light Rank',
             'Dark Rank', 'Staff Rank',
             'Promoted Class',
             'Power Promo', 'Skill Promo', 'Speed Promo', 'Luck Promo', 'Defense Promo',
             'Resistance Promo', 'Constitution Promo', 'Move Promo',
             'Sword Promo', 'Lance Promo', 'Axe Promo', 'Bow Promo', 'Anima Promo',
             'Light Promo', 'Dark Promo', 'Staff Promo'
             ]]
for unit in unitsPy:
  # Each join circumstance is listed distinctly. So HM Rutger and NM Rutger are treated as
  # different units.
  for difficulty in unit['join'].keys():
    
    bases = unit['join'][difficulty]['bases']
    growths = unit['join'][difficulty]['growths']
    items = unit['join'][difficulty]['inventory']
    wranks = unit['join'][difficulty]['wranks']
    promo = unit['promotionBonus'] or {}
    
    unitsCsv.append([
      unit['name'], difficulty,
      bases['hp'], bases['pow'], bases['skl'], bases['spe'], bases['luk'], bases['def'],
      bases['res'], bases['con'], bases['move'],
      growths['hp'], growths['pow'], growths['skl'], growths['spe'], growths['luk'],
      growths['def'], growths['res'],
      unit['join'][difficulty]['startingClass'], unit['join'][difficulty]['startingLevel'],
      si(0, items), si(1, items), si(2, items), si(3, items), si(4, items),
      sh('swords', wranks), sh('lances', wranks), sh('axes', wranks), sh('bows', wranks),
      sh('anima', wranks), sh('light', wranks), sh('dark', wranks), sh('staves', wranks),
      unit['promotedClass'],
      sh('pow', promo), sh('skl', promo), sh('spe', promo), sh('luk', promo), sh('def', promo),
      sh('res', promo), sh('con', promo), sh('move', promo),
      sh('swords', promo), sh('lances', promo), sh('axes', promo), sh('bows', promo),
      sh('anima', promo), sh('light', promo), sh('dark', promo), sh('staves', promo)
    ])

enemiesCsv = [['Chapter',
               'Name', 'Class', 'Level', 'Difficulty',
               'Boss', 'Recruitable', 'Reinforcement',
               'Quantity',
               'HP', 'Power', 'Skill', 'Speed', 'Luck', 'Defense', 'Resistance',
               'Constitution', 'Move',
               'Item 1', 'Item 2', 'Item 3', 'Item 4', 'Item 5']]
for map in mapsPy:
  for e in map['enemies']:
    items = e['inventory']
    enemiesCsv.append([map['number'],
                       e['name'], e['class'], e['level'], e['difficulty'],
                       e['boss'], e['recruitable'], e['reinforcement'],
                       e['quantity'],
                       e['hp'], e['pow'], e['skl'], e['spe'], e['luk'], e['def'], e['res'],
                       e['con'], e['move'],
                       si(0, items), si(1, items), si(2, items), si(3, items), si(4, items)
    ])

weaponsCsv = [['Weapon', 'Type', 'Level', 'Might', 'Weight', 'Hit', 'Crit', 'Range', 'Uses',
               'Price', 'Notes']]
for wpn in weaponsPy:
  weaponsCsv.append([wpn['weapon'], wpn['type'], wpn['level'], wpn['might'], wpn['weight'],
                     wpn['hit'], wpn['crit'], wpn['range'], wpn['uses'], wpn['price'],
                     wpn['notes']
  ])

def write(filename, data):
  with open(filename, 'w', newline = '') as newfile:
    csv.writer(newfile).writerows(data)

print('Writing data to CSV...', end='')

write('enemies.csv', enemiesCsv)
write('units.csv', unitsCsv)
write('weapons.csv', weaponsCsv)

print('Done!')

