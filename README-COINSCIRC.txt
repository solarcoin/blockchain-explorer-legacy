ABE for SolarCoin has been modified to store a list of cold wallet addresses with 
their current balance for display on the landing page. The total amount of SLR in cold
storage is deemed as "non-circulating" and should not be included in market capitalization
calculations. "Coins Circulating" is defined as total coins mined minus coins held in cold
storage wallets. 

There is also an api for providing the value of coins circulating (totalbccirc), this can be 
found in the list of API calls linked to from any ABE page. 


BACKEND DATABASE CHANGES
======================================================
The backend database has a new table added called cold_storage to hold the list of cold 
storage addresses and current address balances. There is an is_active boolean field used
to list the currently used addresses (is_active=1). No addresses will be deleted from the 
cold_storage table. When an address is no longer in use the is_active field is set to 0. 
Currently the cold_storage table is maintained manually whenever money is moved from
cold wallets to hot wallets.

There is also a total_satoshis_coldstorage field added to the chain table. The sum total
of all coins in cold storage is stored in this field. Currently this is updated manually
via SQL UPDATE statement whenever money is moved from cold to hot wallets. This is most easily
done by entering all the new cold wallet addresses and balances and marking previous addresses
as inactive. Values are stored in Satoshis and formatted to whole SLR values for display purposes.

Whenever funds are sent from a cold storage address, any remainding balance is sent to a 
change address and so both the cold_storage table and the chain.total_satoshis_coldstorage 
field will need to be udpated. Sample SQL statements are provided below.


SAMPLE UPDATE/INSERT STATEMENTS
======================================================
The following samples provide guidelines on updating the necessary tables and fields 
when cold storage funds are transferred. The new addresses and their current balance is to be
retrieved from the solarcoin blockchain explorer. Updates should be made in the order shown 
below. 

Note: of course you need to replace the wallet address and balance amounts in the SQL 
statements provided below!


1. Insert new cold wallet addreses in the cold_storage table (balance in satoshis)
	
	insert into cold_storage (base58_address, address_value, is_active) 
          values ('8Kau7tve5QoGKNMHomDr2tHcAMmqUN2zYu',4749499999630000000,1); 

2. Mark previous cold storage address as inactive

        update cold_storage set is_active=0 
	  where base58_address='8YVEmgenUoQi1hCAUdvAtrV2vSEeyi37Xp'

3. Update the total amount of SLR held in cold storage:

	update chain set total_satoshis_coldstorage=
	  (select sum(address_value) from cold_storage where is_active=1)
	  where chain_id=1
