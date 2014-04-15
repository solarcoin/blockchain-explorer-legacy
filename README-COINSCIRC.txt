ABE for SolarCoin has been modified to display a list of cold wallet addresses 
on the landing page. The total amount of SLR in cold storage is deemed as "non-circulating" 
and should not be included in market capitalization calculations. "Coins Circulating" is 
defined as total coins mined minus coins held in cold storage wallets. 

Coins Circulating has been added to the landing page, along with a table of cold wallet
addresses and their current balances. There is also an api for providing the value of coins 
circulating (totalbccirc), this can be found in the list of API calls linked to from any ABE page. 


BACKEND DATABASE CHANGES
======================================================
The backend database has a new table added called cold_storage to hold the list of cold 
storage addresses. There is an is_active boolean field used to list the currently used addresses 
(is_active=1). No addresses will be deleted from the cold_storage table. When an address is no 
longer in use the is_active field is set to 0. Currently the cold_storage table is maintained 
manually whenever money is moved from cold wallets to hot wallets.

Whenever funds are sent from a cold storage address, any remainding balance is sent to a 
change address and so the cold_storage table should be udpated. Sample SQL statements are provided below.


SAMPLE UPDATE/INSERT STATEMENTS
======================================================
The following samples provide guidelines on updating the necessary database records when cold storage 
funds are transferred. The new addresses are to be retrieved from the solarcoin blockchain explorer. 

Note: of course you need to replace the wallet address in the SQL statements provided below!

1. Insert new cold wallet addreses in the cold_storage table (balance in satoshis)
	
	insert into cold_storage (base58_address, chain_id, is_active) 
          values ('8Kau7tve5QoGKNMHomDr2tHcAMmqUN2zYu',1,1); 

2. Mark previous cold storage address as inactive

        update cold_storage set is_active=0 
	  where base58_address='8YVEmgenUoQi1hCAUdvAtrV2vSEeyi37Xp'
