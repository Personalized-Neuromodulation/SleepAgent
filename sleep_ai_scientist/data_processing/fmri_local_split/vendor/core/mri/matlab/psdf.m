function p = psdf(X,f,Fs)

% p = zeros(size(E,2),1);
% Fs = 10000;
% f = 10;
% for i = 1:size(E,2)
% 
% pxx = pmtm(E,4,size(E,1),Fs);
% 
% p = pxx(round(length(pxx)*f/(Fs/2)),:);
% end

if size(X,1) == 1, X = X'; end

Y = fft(X);

L = size(X,1);
P2 = abs(Y/L);
P1 = P2(1:L/2+1,:);
P1(2:end-1,:) = 2*P1(2:end-1,:);

freq = Fs*(0:(L/2))/L;
[~,ind] = min((abs(freq-f)));
p = P1(ind,:);

end