FROM ubuntu

RUN apt-get -y update && apt-get -y install python3
RUN apt-get -y install python3-pip

EXPOSE 5000

WORKDIR /project
COPY requirements.txt requirements.txt
RUN pip3 install --break-system-packages selenium google-generativeai flask


COPY . .

ENTRYPOINT ["python3", "final.py"]




