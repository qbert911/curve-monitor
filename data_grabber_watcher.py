#!/usr/bin/env python3
"""curve"""
# pylint: disable=C0103,C0301,W0105,E0401,R0914,C0411,W0702,C0200,C0116,w0106
import shutil
import json
import time
import cursor
import threading
import argparse
from colorama import Fore, Style, init
from hour_log_process import update_price
from load_contract import load_contract
from curve_functions import curve_header_display, load_curvepools_fromjson, update_curve_pools, curve_boost_check, combined_stats_display
import logging
logging.getLogger().disabled = True
from web3 import Web3
import tripool_calc
import convex_examiner
logging.getLogger().disabled = False
try:
    from curve_rainbowhat_functions import curve_hats_update
    print("Raspberry Pi Hats Found!")
except Exception:
    pass
cursor.hide()
init()

MY_WALLET_ADDRESS = "0x8D82Fef0d77d79e5231AE7BFcFeBA2bAcF127E2B"
INFURA_ID = "69f858948f844da48f4bda85e2811972"
bsc_w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed1.ninicoin.io/'))
infura_w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/'+INFURA_ID))
mylocal_w3 = Web3(Web3.HTTPProvider('http://192.168.0.4:8545'))

file_name = "ghistory.json"
file_nameh = "ghistoryh.json"
myarray = json.load(open(file_name, 'r'))
myarrayh = json.load(open(file_nameh, 'r'))
carray = {"longname": [], "name": [], "invested": [], "currentboost": [], "guageaddress" : [], "swapaddress" : [], "tokenaddress" : []}

csym = Fore.MAGENTA + Style.BRIGHT + "Ç" + Style.RESET_ALL + Fore.CYAN
enter_hit = False

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--Fullheader", help = "Show empty pools in header", action="store_true")
parser.add_argument("-l", "--Local", help = "Local Node Used", action="store_true")
parser.add_argument("-r", "--Readonly", help = "Don't write output to file", action="store_true")
parser.add_argument("-s", "--Small", help = "Small screen size", action="store_true")
parser.add_argument("-b", "--Hourslookback", type=int, help="Use this many hours when calculating pool APR", default=24)
args = parser.parse_args()

def wait_for_local_node_sync(w3):
    while True:
        try:
            a = w3.eth.syncing
            try:
                blockdiff = a['highestBlock']-a['currentBlock']
            except Exception:
                blockdiff = 0
            if a is False or blockdiff < 5:
                break
            print("\rLocal Node has:",blockdiff, "blocks left to catch up\r",end="")
        except Exception:
            print("\rLocal Node communication error", end="")
        time.sleep(10)

def show_ellipsis():
    try:
        bsc_call=load_contract("0x4076CC26EFeE47825917D0feC3A79d0bB9a6bB5c",bsc_w3).claimableRewards(MY_WALLET_ADDRESS).call() #manually downloaded abi due to BSC explorer limitations
        print(Fore.MAGENTA+Style.BRIGHT+"Ë"+Style.RESET_ALL+Fore.BLUE+str(format(round(bsc_call[0][1]/10**18,2),'5.2f').rjust(5))+Style.RESET_ALL, end=' ')
        #print(Fore.BLUE+str(format(round(bsc_call[1][1]/10**18,2),'.2f'))+Fore.WHITE+ "B"+Style.RESET_ALL,end=' - ')
    except Exception:
        print("B", end='')

def show_other_exchanges(w3):
    try:
        crcrv_interest = round(((((load_contract("0xc7Fd8Dcee4697ceef5a2fd4608a7BD6A94C77480", w3).supplyRatePerBlock().call()*4*60*24/10**18)+1)**364)-1)*100, 2)
        aacrv_interest = round(load_contract("0xc7Fd8Dcee4697ceef5a2fd4608a7BD6A94C77480", w3).getReserveData("0xD533a949740bb3306d119CC777fa900bA034cd52").call()[3]/10**25,2)
        print("A"+Fore.BLUE+str(format(aacrv_interest, '4.1f')).rjust(4)+Style.RESET_ALL+"%",
              "C"+Fore.BLUE+str(format(crcrv_interest, '4.1f')).rjust(4)+Style.RESET_ALL+"%", end=' ')  #+"C"+str(crusdc_interest)+"% "+Fore.MAGENTA+Style.BRIGHT+"Ç"+str(format(crcrv_interest, '.2f'))+"%"
    except Exception:
        print("AC", end='')

def show_convex(eoa, extramins, name, label, extrapools, tokenmodindex):
    """cvx display"""
    labels = [ "I", "V", "X", "3"]
    pricefactor = [ carray["token_value_modifyer"][tokenmodindex], myarray[-1]["USD"], myarray[-1]["USDcvx"], myarray[-1]["USD3pool"]]
    buffer=""
    tprofit=0
    for i in range(1,3+extrapools):
        buffer+=Fore.RED+labels[i]+Fore.WHITE
        try:
            buffer+=str(format(round((myarray[-1][name][i]-myarray[eoa][name][i])/(60+extramins)*pricefactor[i]*60*24*365/(myarray[eoa][name][0]*pricefactor[extrapools])*100, 2), '.2f')).rjust(5)+""
            tprofit+=(myarray[-1][name][i]-myarray[eoa][name][i])/(60+extramins)*pricefactor[i]*60*24*365
        except Exception:
            buffer+="xx.xx"
        subtotal=str(format(round(tprofit/(myarray[eoa][name][0]*pricefactor[extrapools])*100, 2), '5.2f')).rjust(5)

    print(Fore.RED+Style.BRIGHT+label+Style.RESET_ALL+subtotal+Style.DIM+"{"+buffer+"}"+Style.RESET_ALL, end=' ')

def show_cvx_rewards(eoa, extramins):
    """cvx staking rewards display"""
    try:
        tprofit=(myarray[-1]["cvxcrv_rewards"][1]-myarray[eoa]["cvxcrv_rewards"][1])/(60+extramins)*myarray[-1]["USDcvxCRV"]*60*24*365
        subtotal=str(format(round(tprofit/(myarray[eoa]["cvxcrv_rewards"][0]*myarray[-1]["USDcvx"])*100, 2), '5.2f')).rjust(5)
    except Exception:
        subtotal="xx.xx"

    print(Fore.RED+Style.BRIGHT+"xCVX"+Style.RESET_ALL+subtotal, end=' ')

def show_curve(eoa, extramins, USD):
    tprofit = 0
    buffer = ""
    _, _, _, minut = map(str, time.strftime("%m %d %H %M").split())
    for i in range(0, len(carray["name"])):
        if carray["currentboost"][i] > 0:
            buffer+=Fore.RED+Style.BRIGHT+carray["name"][i]+Style.RESET_ALL
            try:
                buffer+=str(format(round((myarray[-1][carray["name"][i]+"pool"]-myarray[eoa][carray["name"][i]+"pool"])/(60+extramins)*60*USD*24*365/carray["invested"][i]*100, 2), '.2f')).rjust(5)
            except Exception:
                buffer+="xx.xx"
            try:
                thisdiff = (myarray[-1][carray["name"][i]+"profit"]-myarrayh[-args.Hourslookback-1][carray["name"][i]+"profit"])/(args.Hourslookback+float(int(minut)/60))
            except Exception:
                thisdiff = -1

            if thisdiff >= 0:
                tprofit += thisdiff
                buffer += Style.DIM+Fore.GREEN+str(format(round(thisdiff/60*60*USD*24*365/carray["invested"][i]*100, 2), '.2f')).rjust(5)+" "+Style.RESET_ALL
            else:
                buffer += Style.DIM+Fore.GREEN+"xx.xx "+Style.RESET_ALL
                #print("\n",carray["name"][i],thisdiff,myarray[-1][carray["name"][i]+"profit"],myarrayh[-args.Hourslookback-1][carray["name"][i]+"profit"])

    return tprofit, buffer

def print_status_line(USD, eoa, w3):
    """print main status line"""
    extramins = round((myarray[-1]["raw_time"]-myarray[eoa]["raw_time"])/60)+eoa
    difference = ((myarray[-1]["claim"]+myarray[-1]["trix_rewards"][1]+(myarray[-1]["USDcvx"]*myarray[-1]["trix_rewards"][2]/myarray[-1]["USD"]))-(myarray[eoa]["claim"]+myarray[eoa]["trix_rewards"][1]+(myarray[-1]["USDcvx"]*myarray[eoa]["trix_rewards"][2]/myarray[-1]["USD"])))/(60+extramins)*60
    if args.Small:
        print("\033[A"*3,end='')
    print("\r",end='',flush=True)
    print(myarray[-1]["human_time"], end=' ')
    print("$"+Fore.YELLOW+Style.BRIGHT+f"{USD:.2f}"+Style.RESET_ALL, end = ' - ') #csym+"1"+Style.RESET_ALL+" = "+

    tprofit, buffer = show_curve(eoa, extramins, USD)
    print(Fore.GREEN+Style.BRIGHT+str(format(round((difference)*USD*24*365/(sum(carray["invested"])+(myarray[-1]["trix_rewards"][0]*carray["token_value_modifyer"][carray["longname"].index("tRicrypto")]))*100, 2), '5.2f'))+Style.RESET_ALL+"/", end='')
    print(Fore.YELLOW+str(format(round((tprofit/60*60)*24*365/sum(carray["invested"])*100, 2), '5.2f'))+Style.RESET_ALL+"% APR", end='')
    print(' -',buffer, end='') if not args.Small else print("\n"+buffer)
    #print("H"+csym+format((round(difference, 5)), '.4f')+Style.RESET_ALL, end=' ')
    #print("D"+csym+format((round(difference*24, 2)), '.2f').rjust(5)+Style.RESET_ALL+
    #      "/$"+Fore.YELLOW+f"{round(24*tprofit,2):5.2f}"+Style.RESET_ALL, end= ' ')
    #print("Y"+csym+format((round(difference*24*365, 0)), '.0f').rjust(4)+Style.RESET_ALL+
    #      "/$"+Fore.YELLOW+str(format(round(24*365*tprofit,2), '.0f')).rjust(4)+Style.RESET_ALL, end=' ')
    #show_other_exchanges()
    #show_ellipsis()
    print('[', end='')
    curve_boost_check(carray, w3)
    print('\b] ', end='') if not args.Small else print("")
    show_convex(eoa,extramins,"trix_rewards","xTri", 0, carray["longname"].index("tRicrypto")) #Indicates no third pool and using token_value_modifyer
    tripool_calc.tri_calc(False,-1)
    show_convex(eoa,extramins,"cvx_rewards","xCRV", 1, 0) #Indicates having an extra 3pool and not using token_value_modifyer
    print("["+Fore.CYAN+Style.BRIGHT+f"{((myarray[-1]['USDcvxCRV']-myarray[-1]['USD'])/myarray[-1]['USD'])*100:5.2f}"+Style.RESET_ALL+"%]",end=" ")
    #print("$"+Fore.YELLOW+Style.BRIGHT+f"{myarray[-1]['USDcvxCRV']:.2f}"+Style.RESET_ALL,end=" ")
    show_cvx_rewards(eoa,extramins)
    print("$"+Fore.YELLOW+Style.BRIGHT+f"{myarray[-1]['USDcvx']:.2f}"+Style.RESET_ALL,end=" ", flush=True)
    print("D"+csym+format((round(difference*24, 2)), '.2f').rjust(5)+Style.RESET_ALL,end=" ")
    if extramins >= 0: #air bubble extra minutes
        print(Fore.RED+str(round((myarray[-1]["raw_time"]-myarray[eoa]["raw_time"])/60)+eoa+1)+Style.RESET_ALL, end=' ')
    if eoa > -61:  #fewer than 60 records in the ghistory.json file
        print(Fore.RED+Style.BRIGHT+str(61+eoa).rjust(2)+Style.RESET_ALL, end=' ')
    if myarray[-1]["invested"] != myarray[eoa]["invested"]:
        print(Fore.RED+str(myarray[-1]["invested"] - myarray[eoa]["invested"])+Style.RESET_ALL, end=' ')
    if myarray[-1]["cvx_rewards"][0] != myarray[eoa]["cvx_rewards"][0]:
        print(Fore.RED+str(myarray[-1]["cvx_rewards"][0] - myarray[eoa]["cvx_rewards"][0])+Style.RESET_ALL, end=' ')
    if myarray[-1]["trix_rewards"][0] != myarray[eoa]["trix_rewards"][0]:
        print(Fore.RED+str(myarray[-1]["trix_rewards"][0] - myarray[eoa]["trix_rewards"][0])+Style.RESET_ALL, end=' ')

    return round(((difference*myarray[-1]["USD"])+(tprofit/60*60))*24*365/(sum(carray["invested"])+(myarray[-1]["trix_rewards"][0]*carray["token_value_modifyer"][carray["longname"].index("tRicrypto")]))*100, 2) #display_percent

def key_capture_thread():
    global enter_hit
    enter_hit = False
    input()
    enter_hit = True

def show_headers(w3):
    virutal_price_sum=curve_header_display(myarray, carray, w3, args.Fullheader) if not args.Small else print("\n"*3)
    convex_examiner.convex_header_display(myarray, carray, w3, args.Fullheader) if not args.Small else print("\n"*3)
    combined_stats_display(myarray, carray, w3, virutal_price_sum)
    threading.Thread(target=key_capture_thread, args=(), name='key_capture_thread', daemon=True).start()

def gas_and_sleep(w3):
    firstpass = True                                                            #Prevent header display from outputting in conflict with regular update
    month, day, hour, minut = map(str, time.strftime("%m %d %H %M").split())
    while month+"/"+day+" "+hour+":"+minut == myarray[-1]["human_time"]:        #Wait for each minute to pass to run again
        try:
            print(str("~"+str(round(infura_w3.eth.gasPrice/10**9))+"~").rjust(5), "\b"*6, end="", flush=True)
        except Exception:
            print(str("~"+Fore.RED+Style.BRIGHT+"xxx"+Style.RESET_ALL+"~"), "\b"*6, end="", flush=True)
        if firstpass and minut == "00":
            print("")
            if args.Small:
                print("\n"*3)
        if enter_hit:
            if firstpass:
                print("")
                show_headers(w3)
        firstpass = False
        time.sleep(10)
        month, day, hour, minut = map(str, time.strftime("%m %d %H %M").split())
    if args.Local:
        wait_for_local_node_sync(w3)
        #try:
        #    if w3.eth.syncing:
        #        print("\nLocal Node Sync Issue, Switching to INFURA")
        #        args.Local = False
        #        w3 = infura_w3
        #except Exception:
        #    print("\nLocal Node Connection Issue, Switching to INFURA")
        #    args.Local = False
        #    w3 = infura_w3
def main():
    """monitor various curve contracts"""
    print("Calc Pool APR over hours:",args.Hourslookback)
    print("Read Only Mode:",args.Readonly)
    if not args.Local:
        print("Data Source: Infura")
        w3 = infura_w3
    else:
        print("Data Source: LOCAL (except gas)")
        w3 = mylocal_w3
        print("Local Node Found:", w3.isConnected())
        wait_for_local_node_sync(w3)
    load_curvepools_fromjson(myarray, carray, w3)
    show_headers(w3)
#Main program loop starts here
    while True:
#Check gas price every 10 seconds and wait for a minute to pass
        gas_and_sleep(w3)
#Update dictionary values and price information
        month, day, hour, minut = map(str, time.strftime("%m %d %H %M").split())
        mydict = {"raw_time" : round(time.time()), "human_time": month+"/"+day+" "+hour+":"+minut,
                  "USD" : update_price("curve-dao-token"),
                  "USDcvx" : update_price("convex-finance"),
                  "USD3pool" : update_price("lp-3pool-curve"),
                  "USDcvxCRV" : update_price("convex-crv"),
                  "invested" : sum(carray["invested"])}
        update_curve_pools(mydict, carray, myarray, myarrayh, w3)
        mydict["cvxcrv_rewards"] = convex_examiner.cvxcrv_getvalue(False, myarray, w3)
        mydict["trix_rewards"] = convex_examiner.trix_getvalue(False, myarray, w3)
        mydict["cvx_rewards"] = convex_examiner.cvx_getvalue(False, myarray, w3)
#Keep one hour worth of data in hourly log
        myarray.append(mydict)
        if len(myarray) > 61:
            del myarray[0]
#update information on screen and pi hats when possible
        display_percent = print_status_line(myarray[-1]["USD"], 0 - len(myarray), w3)
        try:
            curve_hats_update(display_percent,
                              str(format(round(update_price("ethereum")),',')).rjust(6),
                              carray["booststatus"])
        except Exception:
            pass
#Output dictionary to minute file
        if not args.Readonly:
            shutil.copyfile(file_name, file_name+".bak")
            json.dump(myarray, open(file_name, "w"), indent=4)
#Output dictionary to hour file on the top of each hour
        if minut == "00" and mydict["claim"] > 1:
            myarrayh.append(mydict)
            if not args.Readonly:
                shutil.copyfile(file_nameh, file_nameh+".bak")
                json.dump(myarrayh, open(file_nameh, "w"), indent=4)

if __name__ == "__main__":
    main()
