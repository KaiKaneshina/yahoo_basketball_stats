import os
import numpy as np
import pandas as pd
import matplotlib
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import datetime
import seaborn as sn
import pprint
import json
import yaml
import dataframe_image as dfi

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

def extract_matchup_scores(league, week):
    """
    extract the matchup stats for each person for the given week


    Parameters
    ----------
    league : class
         yahoo_fantasy_api.league.League
    week : int
         week to extract matchup data from.

    Returns
    -------
    df : pandas dataframe
        contains matchup stats for each person for a given week.

    """
    # parse the stat categories
    statCats = league.stat_categories()
    statCats = [statNames['display_name'] for statNames in statCats]

    # get the current week
    curWeek = league.matchups(week)['fantasy_content']['league'][1]['scoreboard']['0']['matchups']

    # get each team in the matchup
    matchupStats = []

    # get stats for each matchup
    for matchupNumber in range(curWeek['count']):
        matchupNumber = str(matchupNumber)
        curMatchup = curWeek[matchupNumber]['matchup']['0']['teams']
        for team in range(curMatchup['count']):
            team = str(team)
            teamInfo, teamStats = curMatchup[team]['team']
            teamStats = teamStats['team_stats']['stats']
            # separate the FG/FT count stats
            fg = teamStats[0]['stat']['value'].split('/')
            ft = teamStats[2]['stat']['value'].split('/')
            teamStats = [teamStats[1]] + teamStats[3:]
            labeledStats = {statNames:float(statValues['stat']['value'])
                        for statNames,statValues in zip(statCats,teamStats)}
            labeledStats['FGM'] = float(fg[0])
            labeledStats['FGA'] = float(fg[1])
            labeledStats['FTM'] = float(ft[0])
            labeledStats['FTA'] = float(ft[1])
            labeledStats['manager'] = teamInfo[-1]['managers'][0]['manager']['nickname']
            labeledStats['teamName'] = teamInfo[2]['name']
            labeledStats['matchupNumber'] = matchupNumber
            matchupStats.append(labeledStats)

    # once we have all the stats, make a dataframe for the comparison
    df = pd.DataFrame(matchupStats)

    # save the week as the dataframe name
    df.name = week
    return df

def create_matchup_comparison(league, df, visualize=True, saveDir='matchup results'):
    """
     create the matchup matrix to compare each person to each other
     

    Parameters
    ----------
    league : class
        yahoo_fantasy_api.league.League
    df : pandas dataframe
        contains matchup stats for each person for a given week.
    visualize : bool, optional
        decide if you want to visualize the results. The default is True.
    saveDir : str, optional
        directory. The default is 'matchup results'.

    Returns
    -------
    df : pandas dataframe
        contains matchup stats for each person for a given week.
    matchupScore : numpy array
        contains the matchup score for each head to head comparison.
    matchupWinner : numpy array
        winner of the head to head matchups.

    """
    # parse the stat categories
    statCats = league.stat_categories()
    statCats = [statNames['display_name'] for statNames in statCats]

    # split up the categories into TOs and non TOs
    nonTOs = statCats[:-1]
    TOs = statCats[-1]

    # create arrays for the matchup score and the matchup winner
    matchupScore = np.empty((df.shape[0],df.shape[0]),dtype=object)
    matchupWinner = np.zeros((df.shape[0],df.shape[0]))
    for i in range(df.shape[0]):
        curTeam = df.loc[i]
        for j in range(df.shape[0]):
            # compare the rows aka matchups
            vsTeam = df.loc[j]
            curScore = 0
            vsScore = 0
            tieScore = 0
            for cat in nonTOs:
                if curTeam[cat]>vsTeam[cat]:
                    curScore += 1
                elif curTeam[cat]<vsTeam[cat]:
                    vsScore += 1
                # tie case
                else:
                    tieScore += 1
            if curTeam[TOs]<vsTeam[TOs]:
                curScore += 1
            elif curTeam[TOs]>vsTeam[TOs]:
                vsScore += 1
            # tie case
            else:
                tieScore += 1
            if tieScore > 0:
                matchupScore[i,j] = f'{curScore}-{vsScore}-{tieScore}'
            else:
                matchupScore[i,j] = f'{curScore}-{vsScore}'
            if curScore > vsScore:
                matchupWinner[i,j] = 1
            elif vsScore > curScore:
                matchupWinner[i,j] = 0
            # tie case
            else:
                matchupWinner[i,j]= .5

    # get diagonal indices and turn them off
    idxs = np.diag_indices(df.shape[0])

    # 0 them out before doing the biggest winners / losers
    matchupWinner[idxs] = 0
    matchupWinnerCopy = matchupWinner.copy()
    matchupWinnerCopy[matchupWinnerCopy!=1] = 0
    df['totalWins'] = matchupWinnerCopy.sum(axis=1)

    # subtract 1 since you can't play yourself
    matchupWinnerCopy = matchupWinner.copy()
    matchupWinnerCopy[matchupWinnerCopy!=0] = 1
    df['totalLosses'] = (1-matchupWinnerCopy).sum(axis=1) - 1
    # tie case
    matchupWinnerCopy = matchupWinner.copy()
    matchupWinnerCopy[matchupWinnerCopy!=.5] = 0
    matchupWinnerCopy[matchupWinnerCopy==.5] = 1
    df['totalTies'] = matchupWinnerCopy.sum(axis=1)

    # set the diagonals idxs
    matchupWinner[idxs] = -1
    matchupScore[idxs] = 'N/A'

    # fix manager names and team names for saving out data
    df = fix_names_teams(df)

    if visualize:
        # make save directory
        weekSaveDir = os.path.join(saveDir, f'week{df.name}')
        os.makedirs(weekSaveDir,exist_ok=True)

        # save out the dataframe
        df.to_csv(os.path.join(weekSaveDir,'matchupTotals.csv'),index=False)
        dfi.export(df[['manager', 'teamName','totalWins','totalLosses', 'totalTies']], os.path.join(weekSaveDir,'matchupTotalsTable.png'))

        # set colors so that black = -1 / N/A, red = 0 / Loss, green = 1 / Win
        colors = ['black','red','green']
        cmap = matplotlib.colors.LinearSegmentedColormap.from_list("", colors)

        # create labels for the axes
        yAxisLabels = df[['manager', 'teamName']].apply(lambda x: x[0] + '\n' + x[1],axis=1)
        xAxisLabels = df['manager']

        # do plotting
        sn.set(font_scale=1.2)
        f, ax = plt.subplots(figsize=(20,10))
        ax = sn.heatmap(matchupWinner, annot=matchupScore, fmt='', xticklabels = xAxisLabels,
                yticklabels = yAxisLabels, cmap=cmap,cbar=False)

        # add in patches to mark who actually played who in that week
        # get number of unique matchups:
        for m in df['matchupNumber'].unique():
            i,j = df[df['matchupNumber']==m].index
            ax.add_patch(Rectangle((i,j), 1, 1, fill=False, edgecolor='blue', lw=3))
            ax.add_patch(Rectangle((j,i), 1, 1, fill=False, edgecolor='blue', lw=3))
        f.suptitle(f'NBA Fantasy Week {week} Matchups', fontsize = 30)
        ax.set_title('Blue boxes indicate the actual matchups', fontsize = 15)
        plt.yticks(rotation=0)
        plt.savefig(os.path.join(weekSaveDir,'matchups.png'))

    return df, matchupScore, matchupWinner

def fix_names_teams(df):
    """
    edits the dataframe's teamName and manager columns so we can save them our correctly
    

    Parameters
    ----------
    df : pandas dataframe
        contains teamName and manager columns.

    Returns
    -------
    df : pandas dataframe
        modified dataframe.

    """
    for idx, row in df.iterrows():
        manager = row['manager']
        team = row['teamName']
        newManager = ''
        newTeam = ''
        for char in manager:
            if char.isalnum() or char == ' ' or char == '-':
                newManager += char
        for char in team:
            if char.isalnum() or char == ' ' or char == '-':
                newTeam += char
        df.loc[idx, 'manager'] = newManager
        df.loc[idx, 'teamName'] = newTeam
    return df

def highlight_max_and_min_cols(row):
    """
    Parameters
    ----------
    row : row of pandas dataframe


    Returns
    -------
    backgrounds : list
        contains string of cell part and color.

    """
    
    backgrounds = [''] * len(row)
    if row.name=='TO':
        backgrounds = [''] * len(row)
        backgrounds[row.argmin()] = 'background: green'
        backgrounds[row.argmax()] = 'background: red'
        return backgrounds
    else:
        backgrounds[row.argmin()] = 'background: red'
        backgrounds[row.argmax()] = 'background: green'
        return backgrounds

def max_min_stats(league, df, visualize=True, saveDir='matchup results'):
    """
    calculate the min and max stats for each category for the week


    Parameters
    ----------
    league : class
        yahoo_fantasy_api.league.League.
    df : pandas dataframe
        contains matchup stats for each person for a given week.
    visualize : bool, optional
        decide if you want to visualize the results. The default is True.
    saveDir : str, optional
        directory. The default is 'matchup results'.

    Returns
    -------
    maxStatDF : pandas dataframe
        contains the best stat totals for the week.
    minStatDF : pandas dataframe
        contains the worst stat totals for the week

    """
    # parse the stat categories
    origStatCats = league.stat_categories()
    origStatCats = [statNames['display_name'] for statNames in origStatCats]
    statCats = origStatCats + ['FGM', 'FGA', 'FTM', 'FTA']

    # make save directory
    weekSaveDir = os.path.join(saveDir, f'week{df.name}')
    os.makedirs(weekSaveDir,exist_ok=True)

    # compute the highest per category
    maxStatList = []
    maxCats = df[statCats].max()

    for stat, val in maxCats.iteritems():
        managers = df.loc[df[stat]==val, 'manager']
        managers = ', '.join(managers.to_list())
        maxStatList.append([stat, val, managers])

    # save out the data
    maxStatDF = pd.DataFrame(maxStatList, columns = ['Stat', 'Value', 'Manager(s)'])
    maxStatDF.to_csv(os.path.join(weekSaveDir,'maxStats.csv'),index=False)

    # compute lowest per category
    minStatList = []
    minCats = df[statCats].min()

    for stat, val in minCats.iteritems():
        managers = df.loc[df[stat]==val, 'manager']
        managers = ', '.join(managers.to_list())
        minStatList.append([stat, val, managers])

    # save out the data
    minStatDF = pd.DataFrame(minStatList, columns = ['Stat', 'Value', 'Manager(s)'])
    minStatDF.to_csv(os.path.join(weekSaveDir,'minStats.csv'),index=False)

    if visualize:
        dfi.export(minStatDF, os.path.join(weekSaveDir,'minStats.png'))
        dfi.export(maxStatDF, os.path.join(weekSaveDir,'maxStats.png'))

        # make bar charts as well
        # sorted stats
        fig, ax = plt.subplots(3,3, figsize = (20,20))
        fig.subplots_adjust(hspace=.5, wspace = .5)
        for idx, s in enumerate(origStatCats):
            row = idx // 3
            col = idx % 3
            df.sort_values(by = s, inplace = True)
            ax[row,col].bar(df['manager'], df[s])
            ax[row,col].set_title(s)
            ax[row,col].tick_params(axis='x', rotation=75)

        plt.suptitle('Sorted Stats', fontsize = 40)
        plt.savefig(os.path.join(weekSaveDir,'sortedStats.png'))
        plt.close()
        # sorted by manager name
        df.sort_values(by = 'manager', inplace = True)
        fig, ax = plt.subplots(3,3, figsize = (20,20))
        fig.subplots_adjust(hspace=.5, wspace = .5)
        for idx, s in enumerate(origStatCats):
            row = idx // 3
            col = idx % 3
            ax[row,col].bar(df['manager'], df[s])
            ax[row,col].set_title(s)
            ax[row,col].tick_params(axis='x', rotation=75)
        plt.suptitle('Stats', fontsize = 40)
        plt.savefig(os.path.join(weekSaveDir,'stats.png'))
        plt.close()

    return maxStatDF, minStatDF

def get_team_ids(sc, league):
    """
    get the team id, manager, team name, and team object for each team in the league


    Parameters
    ----------
    sc: class
         yahoo oauth object.
    league : class
        yahoo_fantasy_api.league.League.

    Returns
    -------
    teamDF : pandas dataframe
        contains the team id, manager, team name for each team, and team object

    """
    # extract team info from league
    teams = league.teams()
    teamInfo = [[teamID, item['managers'][0]['manager']['nickname'], item['name'], yfa.Team(sc,teamID)]
                for teamID, item in teams.items()]

    # construct dataframe
    teamDF = pd.DataFrame(teamInfo, columns = ['teamID', 'manager','teamName', 'teamObject'])

    return teamDF

def refresh_oauth_file(oauthFile = 'yahoo_oauth.json', sport = 'nba', year = 2021, refresh = False):
    """
    refresh the json file with your consumer secret and consumer key 


    Parameters
    ----------
    oauthFile: str, optional
         file path to file with consumer key and consumer secret. The default is 'yahoo_oauth.json'.
    sport : str, optional
        league for the stats you want. The default is 'nba'
    year: int, optional
        year of the league you want. The default is 2021
    refresh: bool, optional
        flag to use if you want to refresh your oauth key. This is done by deleting the other
        variables in the given oauthFile. The default is false.

    Returns
    -------
    sc : class
        yahoo_oauth object.
    gm : class
        nba fantasy group
    currentLeague: class
        league for the given year

    """
    if refresh:
        ext = os.path.splitext(oauthFile)[1]

        # load in the file
        if ext =='.json':
            # read the current json file
            with open(oauthFile, 'r') as f:
                oauthKeys = json.load(f)
        elif ext =='.yaml':
            # read the current json file
            with open(oauthFile, 'r') as f:
                oauthKeys = yaml.safe_load(f)
        else:
            raise ValueError('Wrong file format for yahoo oauth keys. Please use json or yaml')

        # make a new dictionary with the consumer key and consumer secret variables
        newKeys = {}
        newKeys['consumer_key'] = oauthKeys['consumer_key']
        newKeys['consumer_secret'] = oauthKeys['consumer_secret']

        # delete the original json file before writing a new one
        os.remove(oauthFile)

        # save out the new keys to the original file
        with open(oauthFile, 'w') as f:
            if ext =='.json':
                json.dump(newKeys, f)
            elif ext == '.yaml':
                yaml.dump(newKeys, f)

    # set up authenication
    sc = OAuth2(None, None, from_file=oauthFile)

    # get the nba fantasy group
    gm = yfa.Game(sc, sport)

    # get the current nba fantasy league
    league = gm.league_ids(year=year)

    # get the current league stats based on the current year id
    currentLeague = gm.to_league(league[0])

    return sc, gm, currentLeague

if __name__ == '__main__':

    sc, gm, curLg2021 = refresh_oauth_file(oauthFile = 'yahoo_oauth.json')

    # for each previous week (don't include the current one)
    # yahoo week index starts at 1 so make sure to start looping at 1
    # for week in range(2,curLg2021.current_week()):
    week = curLg2021.current_week()
    # # get the current week matchup stats
    df = extract_matchup_scores(curLg2021, week)
    # calculate matchups
    df, matchupScore, matchupWinner = create_matchup_comparison(curLg2021, df)
    # also compute the highest/lowest per category
    maxStatDF, minStatDF = max_min_stats(curLg2021, df)


    # continue

    # get stat categories we care about
    statCats = curLg2021.stat_categories()
    statCats = [statNames['display_name'] for statNames in statCats]
    teamDF = get_team_ids(sc, curLg2021)
    startDate, endDate = curLg2021.week_date_range(week)
    dateDiff = endDate - startDate
    # get the date ranges with a timestamp of 11:59:59 PM; that way the day has ended
    # so all of the players in non-bench positions with a game will have played
    dateRanges = [datetime.datetime.combine(startDate + datetime.timedelta(days=d), datetime.time(23,59,59))
                for d in range(dateDiff.days + 2)]
    # get sunday from the week before as well to see if there were any add rights before the week started
    previousSunday = datetime.datetime.combine(startDate - datetime.timedelta(days=1), datetime.time(23,59,59))
    # get the roster for previous sunday
    teamDF[previousSunday] = teamDF['teamObject'].apply(lambda teamObject: pd.DataFrame(teamObject.roster(day = previousSunday)))
    # add in stat cats
    for idx in range(teamDF.shape[0]):
        teamDF.loc[idx,previousSunday][statCats] = 0
    # loop through the days and get the roster for each day
    for dIdx, currentDate in enumerate(dateRanges):
        # get the roster for the current date
        currentRoster = teamDF['teamObject'].apply(lambda teamObject: pd.DataFrame(teamObject.roster(day = currentDate)))

        # if it's the first day of the week, save the roster as a total's dataframe
        # also add in statCats
        if dIdx==0:
            teamDF['rosterTotals'] = currentRoster.copy()
            for idx in range(teamDF.shape[0]):
                teamDF.loc[idx,'rosterTotals'][statCats] = 0
                teamDF.loc[idx,'rosterTotals']['dropped'] = False
                teamDF.loc[idx,'rosterTotals']['added'] = False

        # loop through the roster for each team. roster is the same thing as teamDF.loc[idx,currentDate]
        startedPlayerIDs = []
        for idx, roster in enumerate(currentRoster):
            # add stat cats as columns
            currentRoster.loc[idx][statCats] = 0
            # get the player roster for the current day as a list
            startedPlayerIDs.extend(roster['player_id'].to_list())
            # get the players from the previous sunday, aka last week's team as well. Get all players even if they didn't start
            # our comparison will assume that someone would have just been able to start all of their players 
            # from last week for all of the games in the current week
            startedPlayerIDs.extend(teamDF.loc[idx,previousSunday]['player_id'].to_list())
        # get the stats of the unique players
        startedPlayerIDs = list(set(startedPlayerIDs))
        playerStats = curLg2021.player_stats(startedPlayerIDs, 'date', date = currentDate)
        playerStats = pd.DataFrame(playerStats)
        # get the players who actually had games, ignore the player if all stat entries are '-'
        playerStats = playerStats.loc[ ~(playerStats[statCats] == ['-']*9).all(axis=1)]
        # replace categories with '-' entries with 0s
        playerStats.replace('-', value = 0, inplace=True)
        for idx, roster in enumerate(currentRoster):
            # get player ids of those who were on today's roster, since we only want their stats, none of the dropped players stats
            currentPlayers = list(set(playerStats['player_id'].to_list()) & set(roster['player_id']))
            # assign player stats 
            for pID in currentPlayers:
                # check if the player was added this week, since they won't be in the dataframe
                if pID not in teamDF.loc[idx,'rosterTotals']['player_id'].to_list():
                    # add row to dataframe for the added player
                    currentRoster.loc[idx].loc[roster['player_id']==pID, statCats] = playerStats.loc[playerStats['player_id']==pID, statCats].values
                    row = currentRoster.loc[idx].loc[roster['player_id']==pID].copy()
                    row['dropped'] = False
                    row['added'] = True
                    teamDF.loc[idx,'rosterTotals'].loc[len(teamDF.loc[idx,'rosterTotals'].index)] = row.values.tolist()[0]
                # if the player is already in the roster, then just add their stats
                else:
                    teamDF.loc[idx,'rosterTotals'].loc[teamDF.loc[idx,'rosterTotals']['player_id']==pID, statCats] += playerStats.loc[playerStats['player_id']==pID, statCats].values

            # get player ids of those who played from the previous week's roster
            previousPlayers = list(set(playerStats['player_id'].to_list()) & set(teamDF.loc[idx,previousSunday]['player_id']))
            # create sunday roster variable for later
            previousRoster = teamDF.loc[idx,previousSunday]
            # assign player stats 
            for pID in previousPlayers:
                teamDF.loc[idx,previousSunday].loc[previousRoster['player_id']==pID, statCats] += playerStats.loc[playerStats['player_id']==pID, statCats].values

        # mark the dropped players from sunday to sunday
        if dIdx==6:
            for idx, roster in enumerate(teamDF['rosterTotals']):
                # the set subtraction gets the players that were only in the roster from last sunday that aren't in the current sundays
                droppedPlayerIDs = list(set(roster['player_id'].to_list()) - set(currentRoster.loc[idx]['player_id'].to_list()))
                for d in droppedPlayerIDs:
                    teamDF.loc[idx,'rosterTotals'].loc[roster['player_id']==d,'dropped'] = True
        

    df = extract_matchup_scores(curLg2021, week)
    # get the non-% cats: yahoo doesn't give the FTA/FTM and FGA/FGM values...
    countingStats = statCats[2:]
    teamDF[countingStats] = 0
    teamDF['adds'] = 0
    countingResultsCols = ['improved categories', 'worsened categories']
    teamDF[countingResultsCols] = 0

    # create comparison difference between team A and team B
    matchupDiffs = {}
    for m in df['matchupNumber'].unique():
        i,j = df[df['matchupNumber']==m].index
        # save data as stats, opponent, matchup numbner
        matchupDiffs[df.loc[i, 'manager']] = [df.loc[i, countingStats] - df.loc[j, countingStats], df.loc[j, 'manager'], m]
        matchupDiffs[df.loc[j, 'manager']] = [df.loc[j, countingStats] - df.loc[i, countingStats], df.loc[i, 'manager'], m]

    addsDF = teamDF.copy()
    addedCountingStatsDict = {}
    # for each roster, calculate the totals for the week
    for idx in range(teamDF.shape[0]):
        oldRoster = teamDF.loc[idx, previousSunday].copy()
        currentRoster = teamDF.loc[idx, 'rosterTotals'].copy()
        curManager = teamDF.loc[idx,'manager']

        addsDF.loc[idx, 'adds'] = currentRoster['added'].sum()

        weekTotalsDifference, opponentManager, matchupNumber = matchupDiffs[curManager]
        addsDF.loc[idx, 'matchupNumber'] = matchupNumber
        addsDF.loc[idx, 'opponent'] = opponentManager
        teamDF.loc[idx, 'adds'] = currentRoster['added'].sum()
        addedPlayerStats = currentRoster[countingStats].sum() - oldRoster[countingStats].sum() 
        teamDF.loc[idx, countingStats] = addedPlayerStats
        addedCountingStatsDict[curManager] = [addedPlayerStats, weekTotalsDifference]
        # get the added player boost for each category
        playerBoost = []
        for c in range(len(addedPlayerStats)):
            if c == len(addedPlayerStats) - 1:
                # for the TO category, if the week total difference is more than the added players TOs
                # removing them wouldn't make the difference negative for you to win
                if weekTotalsDifference[c] > addedPlayerStats[c]:
                    playerBoost.append('-')
                # in the opposite case, you added players whose TOs were more than the difference, so 
                # you caused yourself to lose the week...
                else:
                    playerBoost.append(addedPlayerStats[c] - weekTotalsDifference[c])
            else:
                # if the week total is negative for the non-TO category,
                # then you wouldn't have won with your adds
                if weekTotalsDifference[c] < 0 :
                    playerBoost.append('-')
                else:
                    # difference closed with your adds
                    playerBoost.append(addedPlayerStats[c] - weekTotalsDifference[c])

        addsDF.loc[idx, countingStats] = playerBoost
        # get the non TOs and TOs comparisons
        improvement = sum(teamDF.loc[idx, countingStats[:-1]] > 0) + int(teamDF.loc[idx, countingStats[-1]] < 0)
        worsened = sum(teamDF.loc[idx, countingStats[:-1]] < 0) + int(teamDF.loc[idx, countingStats[-1]] > 0)
        teamDF.loc[idx, 'improved categories'] = improvement
        teamDF.loc[idx, 'worsened categories'] = worsened
    
    finalComparisonDF = teamDF[['manager', 'teamName', 'adds'] + countingStats + countingResultsCols]

    saveDir='matchup results'
    weekSaveDir = os.path.join(saveDir, f'week{week}')
    os.makedirs(weekSaveDir,exist_ok=True)


    finalComparisonDF = fix_names_teams(finalComparisonDF)
    finalComparisonDF.to_csv(os.path.join(weekSaveDir,'bestManager.csv'), index=False)
    finalComparisonDF = finalComparisonDF.style.apply(highlight_max_and_min_cols,subset = countingStats,axis= 0)
    dfi.export(finalComparisonDF, os.path.join(weekSaveDir,'bestManager.png'))

    def highlight_adds(cols, addedCountingStatsDict):


        addedPlayerStats, weekTotalsDifference = addedCountingStatsDict[cols['manager']]
        playerBoost = ['']
        for c in range(len(cols[1:])):
            if c == len(addedPlayerStats) - 1:
                # you already won the week, nice job
                if weekTotalsDifference[c] < 0 :
                    playerBoost.append('background: green')
                # for the TO category, if the week total difference is more than the added players TOs
                # removing them wouldn't make the difference negative for you to win
                elif weekTotalsDifference[c] > addedPlayerStats[c]:
                    playerBoost.append('background: yellow')

                # in the opposite case, you added players whose TOs were more than the difference, so 
                # you caused yourself to lose the week...
                else:
                    playerBoost.append('background: red')

            else:
                # if the week total is negative for the non-TO category,
                # then you wouldn't have won with your adds
                if weekTotalsDifference[c] < 0 :
                    playerBoost.append('background: red')
                # if you won the category, but the added player stats are less than this, you would've won anyways...
                elif weekTotalsDifference[c] > addedPlayerStats[c]:
                    playerBoost.append('background: yellow')
                else:
                    # difference closed with your adds
                    playerBoost.append('background: green')

        return playerBoost

    finalAddsDF = addsDF[['manager', 'teamName', 'opponent', 'matchupNumber', 'adds'] + countingStats]
    finalAddsDF.sort_values(by='matchupNumber', inplace=True)
    finalAddsDF = fix_names_teams(finalAddsDF)
    finalAddsDF.to_csv(os.path.join(weekSaveDir,'addsComparison.csv'), index=False)
    finalAddsDF = finalAddsDF.style.apply(highlight_adds, addedCountingStatsDict = addedCountingStatsDict, subset = ['manager'] + countingStats,axis= 1)
    dfi.export(finalAddsDF, os.path.join(weekSaveDir,'addsComparison.png'))
