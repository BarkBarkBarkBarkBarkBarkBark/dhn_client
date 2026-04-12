%
% netcom script, to listen to "CSC1" and get timestamps in realtime, to
% send start/stop recording events
%
% start this script, run the entire extraction. Then, interrupt
% with ctrl-c and execute the last 2 lines manually to close the
% connection. Inspect the history variable to see if all events were
% correctly started/stopped.
%
% has to be run on a machine with at least 2 CPUs, so that matlab has one
% CPU and cheetah the other one. MATLAB is polling, thus the high CPU load.
%
%urut/feb09

%== parameters

fname = 'V:\dataRawEpilepsy\P60CS_Jie\MemSeg_TimeDiscrim\timestampsInclude.txt'
serverName = 'localhost';
objectIndex = 10;   % this object needs to be a microwire channel (full sampling rate)

%=========================

%timestampsExperiments = [ 4681793550 5080568088 ];
timestampsExperiments=dlmread(fname);
%timestampsExperiments(:,1) = timestampsExperiments(:,1)-1e6;   % start 1s before exp starts

if isempty(timestampsExperiments)
    error(['timestamps file not found: ' fname]);
end

%
succeeded = NlxDisconnectFromServer();

%============                
disp(sprintf('Connecting to %s...', serverName));
succeeded = NlxConnectToServer(serverName);
if succeeded ~= 1
    error(sprintf('FAILED connect to %s. Exiting script.', serverName));
    %return;
else
    disp(sprintf('Connected to %s.', serverName));
end

%Identify this program to the server we're connected to.
succeeded = NlxSetApplicationName('OSORT postprocessing exps');
if succeeded ~= 1
    error('FAILED set the application name');
else
    disp 'PASSED set the application name'
end

%get a list of all objects in Cheetah, along with their types.
[succeeded, cheetahObjects, cheetahTypes] = NlxGetCheetahObjectsAndTypes;
if succeeded == 0
    error('FAILED get cheetah objects and types');
else
    disp 'PASSED get cheetah objects and types'
end

%open up a stream for all objects
%for index = 1:length(cheetahObjects)

succeeded = NlxOpenStream(cheetahObjects(objectIndex));

if succeeded == 0
        error(sprintf('FAILED to open stream for %s', char(cheetahObjects(objectIndex))));
        %break;
end

%end;
if succeeded == 1
    disp 'PASSED open stream for all current objects'
end

%send out an event so that there is something in the event buffer when
%this script queries the event buffer  You can use NlxSendCommand to send
%any Cheetah command to Cheetah.
[succeeded, cheetahReply] = NlxSendCommand('-PostEvent "NetCom Client started" 99 11');
if succeeded == 0
    error( 'FAILED to send command' );
else
    disp 'PASSED send command'
end



%% start acquisition
[succeeded, cheetahReply] = NlxSendCommand('-StartAcquisition');

%%
objectToRetrieve = char(cheetahObjects(objectIndex));

allTimes=[];

currentState=0; % 0->not running (look in start). 1->running (look in stop)

Fs=32000;  % sampling rate in new ATLAS system
blockSize = round(512 * 1e6/Fs); %in us, for 32556Hz

history=[];

%start recording asap (debugging only)
%[succeeded, cheetahReply] = NlxSendCommand('-StartRecording');
%currentState=1;

pass=0;
c=0;
maxi=0;
running=1;
while(running)
   [succeeded,dataArray, timeStampArray, channelNumberArray, samplingFreqArray, numValidSamplesArray, numRecordsReturned, numRecordsDropped ] = NlxGetNewCSCData(objectToRetrieve);

   if succeeded == 0
      disp(sprintf('FAILED to get new data for CSC stream %s on pass %d', objectToRetrieve, pass));
      %keyboard;
   else
      if numRecordsReturned==0
          pause(0.05);
          c=c+1;
          if c>maxi,
              maxi=c;
              fprintf('c maxi: %d\n',maxi);
          end
          if c>100
              running=0;
          end
          continue;
      else
          c=0;
      end
      
      disp(sprintf('Retrieved %d CSC records for %s with %d dropped.', numRecordsReturned, objectToRetrieve, numRecordsDropped));
      
      %process the timestamps
      if currentState==0
         toSearch=timestampsExperiments(:,1); 
      else
         toSearch=timestampsExperiments(:,2); 
      end
      
      if length(timeStampArray)>0

          if timeStampArray(1)>0
              for k=1:length( toSearch )
                  ind=find( timeStampArray>= toSearch(k) & timeStampArray<=toSearch(k)+ blockSize );
                  if ~isempty(ind)
                      ind=ind(1);

                      if currentState==0
                          disp([' Found match, start recording. Ind=' num2str(timeStampArray(ind)) ]);
                        
                          msg=['StartRecording for Time=' num2str(toSearch(k))];
                          
                          [succeeded, cheetahReply] = NlxSendCommand('-StartRecording');
                          [succeeded, cheetahReply] = NlxSendCommand(['-PostEvent "' msg '" 99 11']);
                          currentState=1;
                          
                          history=[ history; [0 toSearch(k) k] ];
                      else
                          disp([' Found match, stop recording. Ind=' num2str(timeStampArray(ind)) ]);

                          msg=['StopRecording for Time=' num2str(toSearch(k))];
                          
                          [succeeded, cheetahReply] = NlxSendCommand('-StopRecording');
                          [succeeded, cheetahReply] = NlxSendCommand(['-PostEvent "' msg '" 99 11']);
                          currentState=0;

                          history=[ history; [1 toSearch(k) k] ];
                      end
                  %else
                  %    disp( [ 'no match from/to:' num2str( timeStampArray(1)) ' to ' num2str(timeStampArray(end)) ]);
                  end
              end
          else
             running = 0;
          end
      end

      % c=c+1
      %allTimes{c} = timeStampArray;
   end
   
   %if c>100
   %    running=0;
   %end
end

%close out
succeeded = NlxCloseStream(cheetahObjects(objectIndex));
succeeded = NlxDisconnectFromServer();
% 
% %======
% [succeeded, cheetahReply] = NlxSendCommand('-StartRecording');
% 
% [succeeded, cheetahReply] = NlxSendCommand('-StopRecording');
% 
% 
% pause(3);
% 
% %close all open streams before disconnecting
% for index = 1:length(cheetahObjects)
%     succeeded = NlxCloseStream(cheetahObjects(index));
%     if succeeded == 0
%         disp(sprintf('FAILED to close stream for %s', char(cheetahObjects(index))));
%         break;
%     end
% end;
% if succeeded == 1
%     disp 'PASSED close stream for all current objects'
% end
% 
% 
% %Disconnects from the server and shuts down NetCom
% succeeded = NlxDisconnectFromServer();
% if succeeded ~= 1
%     disp 'FAILED disconnect from server'
% else
%     disp 'PASSED disconnect from server'
% end
% 
% %remove all vars created in this test script
% clear