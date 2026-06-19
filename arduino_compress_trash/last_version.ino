const int RPWM = 6;
const int LPWM = 5;

const int TRIG_PIN = 9;
const int ECHO_PIN = 10;

const int CURRENT_PIN = A0;
const int CURRENT_THRESHOLD = 530;
const int CURRENT_CONFIRM_COUNT = 5;

const float EMPTY_THRESHOLD_CM = 35.0;
const float FULL_THRESHOLD_CM = 16.0;
const float STABILITY_THRESHOLD_CM = 5.0;

// Measure these experimentally
const unsigned long EXTEND_TIME_MS  = 20000;
const unsigned long RETRACT_TIME_MS = 20000;

bool binFullLocked = false;
bool obstructionLocked = false;

void extendActuator()
{
  analogWrite(RPWM, 0);
  analogWrite(LPWM, 255);
}

void retractActuator()
{
  analogWrite(RPWM, 255);
  analogWrite(LPWM, 0);
}

void stopActuator()
{
  analogWrite(RPWM, 0);
  analogWrite(LPWM, 0);
}

float readDistanceCM()
{
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);

  if(duration == 0)
    return 999.0;

  return duration * 0.0343 / 2.0;
}

float medianDistanceCM()
{
  const int N = 7;
  float values[N];

  for(int i = 0; i < N; i++)
  {
    values[i] = readDistanceCM();

    // HC-SR04 recommendation
    delay(60);
  }

  // Sort
  for(int i = 0; i < N - 1; i++)
  {
    for(int j = i + 1; j < N; j++)
    {
      if(values[j] < values[i])
      {
        float temp = values[i];
        values[i] = values[j];
        values[j] = temp;
      }
    }
  }

  return values[N / 2];
}

bool needsCompression()
{
  const int NUM_CHECKS = 10;

  float sum = 0;
  float minDist = 999;
  float maxDist = 0;

  Serial.println("CHECKING BIN LEVEL...");

  for(int i = 0; i < NUM_CHECKS; i++)
  {
    float d = medianDistanceCM();

    Serial.print("Reading ");
    Serial.print(i + 1);
    Serial.print(": ");
    Serial.print(d);
    Serial.println(" cm");

    sum += d;

    if(d < minDist)
      minDist = d;

    if(d > maxDist)
      maxDist = d;

    delay(100);
  }

  float avgDist = sum / NUM_CHECKS;
  float range = maxDist - minDist;

  Serial.print("Average Distance = ");
  Serial.print(avgDist);
  Serial.println(" cm");

  Serial.print("Range = ");
  Serial.print(range);
  Serial.println(" cm");

  if(avgDist < FULL_THRESHOLD_CM &&
     range < STABILITY_THRESHOLD_CM)
  {
    Serial.println("FULL BIN CONFIRMED");
    return true;
  }

  Serial.println("BIN NOT FULL OR NOT STABLE");
  return false;
}

bool compressCycle()
{
  bool currentLimitReached = false;
  Serial.println("COMPRESSING");
  sendStatus("COMPRESSING");
  extendActuator();

  unsigned long startTime = millis();
  int highCurrentCount = 0;

  while(millis() - startTime < EXTEND_TIME_MS)
  {
      int adc = analogRead(CURRENT_PIN);

      Serial.print("ADC = ");
      Serial.println(adc);

      if(adc > CURRENT_THRESHOLD)
      {
          highCurrentCount++;
      }
      else
      {
          highCurrentCount = 0;
      }

      if(highCurrentCount >= CURRENT_CONFIRM_COUNT)
      {
          Serial.println("CURRENT LIMIT REACHED");
          sendStatus("CURRENT_LIMIT");

          currentLimitReached = true;
          break;
      }

      delay(20);
  }

  stopActuator();

  Serial.println("HOLDING");
  sendStatus("HOLDING");
  delay(2000);

  Serial.println("RETRACTING");
  sendStatus("RETRACTING");
  retractActuator();
  delay(RETRACT_TIME_MS);
  stopActuator();

  Serial.println("DONE");
  return currentLimitReached;
}

void sendStatus(const char* status)
{
  Serial.print(",\"status\":\"");
  Serial.print(status);
  Serial.println("\"}");
}

void setup()
{
  Serial.begin(115200);

  pinMode(RPWM, OUTPUT);
  pinMode(LPWM, OUTPUT);

  pinMode(CURRENT_PIN, INPUT);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  stopActuator();

  // Home the actuator to retracted position on startup
  Serial.println("HOMING...");
  sendStatus("HOMING");
  retractActuator();
  delay(5000);
  stopActuator();
  Serial.println("HOMING DONE");

  Serial.println("SMART TRASH COMPACTOR READY");
  sendStatus("IDLE");
}

void loop()
{
  if(obstructionLocked)
  {
      float d = medianDistanceCM();
      Serial.print("Waiting for obstruction removal. Distance = ");
      Serial.println(d);

      if(d > EMPTY_THRESHOLD_CM)
      {
          Serial.println("TRASH CONTENT CHANGED");
          Serial.println("RESUMING NORMAL OPERATION");
          sendStatus("IDLE");

          obstructionLocked = false;
      }

      delay(2000);
      return;
  }
  if(binFullLocked)
  {
    float d = medianDistanceCM();

    Serial.print("Waiting for bin to be emptied. Distance = ");
    Serial.println(d);

    // Bin considered emptied
    if(d > EMPTY_THRESHOLD_CM)
    {
        Serial.println("BIN EMPTIED");
        sendStatus("IDLE");

        binFullLocked = false;
    }

    delay(2000);
    return;
  }

  if(needsCompression())
  {
    Serial.println("COMPRESSION NEEDED");

    bool currentLimit1 = compressCycle();
    delay(2000);

    if(!needsCompression())
    {
      Serial.println("BIN OK");
      sendStatus("OK");
      delay(5000);
      return;
    }

    Serial.println("SECOND COMPRESSION ATTEMPT");

    bool currentLimit2 = compressCycle();
    delay(2000);

    if(!needsCompression())
    {
        Serial.println("BIN OK");
        sendStatus("OK");
        delay(5000);
        return;
    }

    if(currentLimit1 && currentLimit2)
    {
        Serial.println("************************");
        Serial.println("REMOVE OBSTRUCTION");
        Serial.println("CHECK TRASH CONTENT");
        Serial.println("************************");

        sendStatus("OBSTRUCTION");

        obstructionLocked = true;

        return;
    }

    Serial.println("****************");
    Serial.println("BIN FULL");
    Serial.println("EMPTY BIN");
    Serial.println("****************");

    sendStatus("BIN_FULL");

    // LOCK SYSTEM
    binFullLocked = true;

    return;
  }
  else
  {
    Serial.println("BIN OK");
    sendStatus("IDLE");
  }

  delay(1000);
}